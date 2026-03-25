from typing import List, Optional
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist

from user_calendar.adapters.orm.models import (
    CalendarEventModel,
    CategoryModel,
    UserCalendarModel,
)
from user_calendar.application.ports.repository import (
    CalendarEventRepository,
    CategoryRepository,
    UserCalendarRepository,
)
from user_calendar.domain.entities import CalendarEvent, Category, UserCalendar
from user_calendar.domain.value_objects import (
    CalendarId,
    CalendarProvider,
    CategoryId,
    CreatedAt,
    EventId,
    UserId,
)


class DjangoUserCalendarRepository(UserCalendarRepository):
    def save(self, calendar: UserCalendar) -> None:
        UserCalendarModel.objects.update_or_create(
            ory_identity_id=calendar.user_id.value,
            defaults={
                "calendar_id": calendar.calendar_id.value,
                "provider": calendar.provider.value,
                "google_calendar_id": calendar.google_calendar_id,
                "access_token": calendar.access_token,
                "refresh_token": calendar.refresh_token,
            },
        )

    def find_by_user_id(self, user_id: UserId) -> Optional[UserCalendar]:
        try:
            model = UserCalendarModel.objects.get(ory_identity_id=user_id.value)
        except ObjectDoesNotExist:
            return None

        return UserCalendar(
            calendar_id=CalendarId(model.calendar_id),
            user_id=UserId(model.ory_identity_id),
            provider=CalendarProvider(model.provider),
            created_at=CreatedAt(model.created_at),
            google_calendar_id=model.google_calendar_id,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
        )

    def find_by_id(self, calendar_id: CalendarId) -> Optional[UserCalendar]:
        try:
            model = UserCalendarModel.objects.get(calendar_id=calendar_id.value)
        except ObjectDoesNotExist:
            return None

        return UserCalendar(
            calendar_id=CalendarId(model.calendar_id),
            user_id=UserId(model.ory_identity_id),
            provider=CalendarProvider(model.provider),
            created_at=CreatedAt(model.created_at),
            google_calendar_id=model.google_calendar_id,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
        )


class DjangoCategoryRepository(CategoryRepository):
    def save(self, category: Category) -> None:
        CategoryModel.objects.update_or_create(
            id=category.category_id.value,
            defaults={
                "ory_identity_id": category.user_id.value,
                "name": category.name,
                "color": category.color,
            },
        )

    def find_by_user_id(self, user_id: UserId) -> List[Category]:
        rows = CategoryModel.objects.filter(ory_identity_id=user_id.value).order_by(
            "created_at"
        )
        return [
            Category(
                category_id=CategoryId(r.id),
                user_id=UserId(r.ory_identity_id),
                name=r.name,
                color=r.color,
                created_at=CreatedAt(r.created_at),
            )
            for r in rows
        ]

    def find_by_id(self, category_id: CategoryId) -> Optional[Category]:
        try:
            r = CategoryModel.objects.get(id=category_id.value)
        except ObjectDoesNotExist:
            return None

        return Category(
            category_id=CategoryId(r.id),
            user_id=UserId(r.ory_identity_id),
            name=r.name,
            color=r.color,
            created_at=CreatedAt(r.created_at),
        )

    def delete(self, category_id: CategoryId) -> None:
        CategoryModel.objects.filter(id=category_id.value).delete()


class DjangoCalendarEventRepository(CalendarEventRepository):
    def save(self, event: CalendarEvent) -> None:
        model, _ = CalendarEventModel.objects.update_or_create(
            id=event.event_id.value,
            defaults={
                "ory_identity_id": event.user_id.value,
                "title": event.title,
                "start_at": event.start_at,
                "end_at": event.end_at,
                "estimated_cost": event.estimated_cost,
                "created_at": event.created_at.value,
            },
        )
        cat_ids = [cid.value for cid in event.category_ids]
        cats = CategoryModel.objects.filter(id__in=cat_ids, ory_identity_id=event.user_id.value)
        model.categories.set(cats)

    def find_by_user_id(self, user_id: UserId) -> List[CalendarEvent]:
        rows = CalendarEventModel.objects.prefetch_related("categories").filter(
            ory_identity_id=user_id.value
        ).order_by("start_at")
        return [
            CalendarEvent(
                event_id=EventId(r.id),
                user_id=UserId(r.ory_identity_id),
                title=r.title,
                start_at=r.start_at,
                end_at=r.end_at,
                created_at=CreatedAt(r.created_at),
                estimated_cost=r.estimated_cost,
                category_ids=[CategoryId(c.id) for c in r.categories.all()],
            )
            for r in rows
        ]

    def find_by_id(self, event_id: EventId) -> Optional[CalendarEvent]:
        try:
            r = CalendarEventModel.objects.prefetch_related("categories").get(
                id=event_id.value
            )
        except ObjectDoesNotExist:
            return None

        return CalendarEvent(
            event_id=EventId(r.id),
            user_id=UserId(r.ory_identity_id),
            title=r.title,
            start_at=r.start_at,
            end_at=r.end_at,
            created_at=CreatedAt(r.created_at),
            estimated_cost=r.estimated_cost,
            category_ids=[CategoryId(c.id) for c in r.categories.all()],
        )

    def update(self, event: CalendarEvent, category_ids: list[UUID]) -> None:
        m = CalendarEventModel.objects.get(id=event.event_id.value)

        m.title = event.title
        m.start_at = event.start_at
        m.end_at = event.end_at
        m.estimated_cost = event.estimated_cost
        m.save()

        m.categories.set(category_ids)

    def delete(self, event_id: EventId) -> None:
        CalendarEventModel.objects.filter(id=event_id.value).delete()
