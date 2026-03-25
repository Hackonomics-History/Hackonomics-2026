import logging

from events.application.ports.event_repository import EventRepository
from events.domain.entities import DomainEvent
from events.infra.kafka.producer import KafkaEventProducer

logger = logging.getLogger(__name__)


class KafkaEventRepository(EventRepository):
    """High-volume event path: writes directly to Kafka, bypasses the DB.

    Dam logic — prevents write saturation on hot paths (e.g. user-activity
    logs) by buffering in Kafka instead of the relational DB.  There is no
    transactional guarantee: if Kafka is unavailable the event is dropped and
    logged.  Use OutboxEventRepository for events that require durability.
    """

    def __init__(self):
        self._producer = KafkaEventProducer()

    def save(self, event: DomainEvent) -> None:
        delivered = self._producer.publish(
            "user-activities",
            {
                "event_id": event.event_id,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "event_type": event.event_type,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": event.payload,
            },
        )
        if not delivered:
            logger.error(
                "KafkaEventRepository: dropped event %s (delivery failed)",
                event.event_id,
            )

    def get_by_id(self, event_id):
        raise NotImplementedError("KafkaEventRepository is write-only")

    def mark_published(self, event):
        raise NotImplementedError("KafkaEventRepository is write-only")
