from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class CalendarId:
    value: UUID

    @staticmethod
    def new():
        return CalendarId(uuid4())


@dataclass(frozen=True)
class UserId:
    value: str  # Ory identity UUID string


@dataclass(frozen=True)
class CalendarProvider:
    value: str  # "google"

    @staticmethod
    def google() -> "CalendarProvider":
        return CalendarProvider("google")


@dataclass(frozen=True)
class CreatedAt:
    value: datetime

    @staticmethod
    def now() -> "CreatedAt":
        return CreatedAt(datetime.now(timezone.utc))


# Categories
@dataclass(frozen=True)
class CategoryId:
    value: UUID

    @staticmethod
    def new() -> "CategoryId":
        return CategoryId(uuid4())


# Events
@dataclass(frozen=True)
class EventId:
    value: UUID

    @staticmethod
    def new() -> "EventId":
        return EventId(uuid4())
