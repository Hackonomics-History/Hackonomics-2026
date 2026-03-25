from events.application.ports.event_repository import EventRepository
from events.domain.entities import DomainEvent
from events.infra.outbox_models import OutboxEvent


class OutboxEventRepository(EventRepository):
    def save(self, event: DomainEvent):
        OutboxEvent.objects.create(
            event_id=event.event_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload=event.payload,
            published=False,
        )

    def get_by_id(self, event_id):
        return OutboxEvent.objects.get(id=event_id)

    def mark_published(self, event):
        event.published = True
        event.save(update_fields=["published"])
