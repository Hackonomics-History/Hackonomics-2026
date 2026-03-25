import logging
import signal
import time

from django.db import transaction

from events.infra.kafka.producer import KafkaEventProducer
from events.infra.outbox_models import OutboxEvent

logger = logging.getLogger(__name__)

TOPIC = "user-activities"
BATCH_SIZE = 100
POLL_INTERVAL = 1  # seconds between batch cycles
_RUNNING = True


def _shutdown_handler(sig, frame):
    global _RUNNING
    _RUNNING = False
    logger.info("Outbox worker: shutdown signal received, stopping after current batch")


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)


def process_outbox_batch() -> int:
    """Fetch up to BATCH_SIZE unpublished events and relay them to Kafka.

    At-least-once semantics:
      - Each event is marked published=True ONLY after a confirmed delivery
        report from the broker (producer.publish() returns True).
      - On the first delivery failure the batch halts; the failed event and
        all subsequent events remain unpublished and will be retried next cycle.
      - Consumers must de-duplicate by event_id to handle redelivery.

    Returns the number of events successfully published in this batch.
    """
    events = (
        OutboxEvent.objects.filter(published=False)
        .order_by("created_at")[:BATCH_SIZE]
    )

    if not events:
        return 0

    producer = KafkaEventProducer()
    published_count = 0

    for event in events:
        message = {
            "event_id": event.event_id,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "event_type": event.event_type,
            "payload": event.payload,
            "occurred_at": event.created_at.isoformat(),
        }

        delivered = producer.publish(TOPIC, message)

        if delivered:
            # Mark published only after broker ACK — at-least-once guarantee
            with transaction.atomic():
                event.published = True
                event.save(update_fields=["published"])
            published_count += 1
        else:
            logger.error(
                "Outbox worker: halting batch at event_id=%s — Kafka unavailable",
                event.event_id,
            )
            break  # retry this and remaining events next cycle

    return published_count


def run_worker() -> None:
    logger.info("Outbox worker started (batch_size=%d, topic=%s)", BATCH_SIZE, TOPIC)
    while _RUNNING:
        try:
            count = process_outbox_batch()
            if count:
                logger.info("Outbox worker: published %d event(s)", count)
        except Exception as exc:
            logger.error("Outbox worker: unexpected error: %s", type(exc).__name__)
        time.sleep(POLL_INTERVAL)
    logger.info("Outbox worker stopped")
