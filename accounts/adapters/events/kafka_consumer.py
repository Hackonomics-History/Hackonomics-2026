import json
import logging

from confluent_kafka import Consumer, KafkaError
from django.conf import settings
from django.db import transaction

from accounts.application.usecases.event_router import AccountEventRouter
from events.infra.kafka.retry_router import publish_to_retry

logger = logging.getLogger(__name__)

TOPIC = "user-activities"


def _retry_attempt(msg) -> int:
    """Read the retry_attempt header from a Kafka message (default 0)."""
    for key, value in (msg.headers() or []):
        if key == "retry_attempt":
            try:
                return int(value.decode())
            except (ValueError, UnicodeDecodeError):
                return 0
    return 0


def start_kafka_consumer() -> None:
    """Consume events from Kafka with bounded retry via tiered retry topics.

    Delivery semantics
    ------------------
    - auto.commit is disabled; offsets are committed manually after each outcome.
    - Processing success → commit offset, continue.
    - Processing failure → route to user-activities.retry-1 (or higher tier if
      already a retry message), then commit offset on the source topic.
      The message is NOT redelivered on this topic; the retry consumer handles it.
    - Decode error      → route directly to user-activities.dlt (not retried —
      a malformed payload will never recover), then commit offset.

    Consumers must de-duplicate by event_id to handle at-least-once redelivery
    across retry tiers.
    """
    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "accounts-service",
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([TOPIC])
    router = AccountEventRouter()
    logger.info("Kafka Account Consumer started (topic=%s)", TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Kafka consumer error: %s", msg.error())
                continue

            # ── Decode ──────────────────────────────────────────────────────
            try:
                event = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.error(
                    "Kafka message decode error: %s | "
                    "topic=%s partition=%d offset=%d — routing to DLT",
                    type(exc).__name__,
                    msg.topic(),
                    msg.partition(),
                    msg.offset(),
                )
                # Decode errors go directly to DLT — they are not transient.
                publish_to_retry(msg.value(), msg.headers(), attempt=3)
                consumer.commit(asynchronous=False)
                continue

            # ── Process ─────────────────────────────────────────────────────
            try:
                with transaction.atomic():
                    router.route(event)
                consumer.commit(asynchronous=False)

            except Exception as exc:
                attempt = _retry_attempt(msg)
                logger.error(
                    "Event processing failed (event_id=%s attempt=%d): %s — routing to retry",
                    event.get("event_id"),
                    attempt,
                    type(exc).__name__,
                )
                # Route to the next retry tier; commit past this message so the
                # main consumer group is never blocked by a single bad event.
                publish_to_retry(msg.value(), msg.headers(), attempt + 1)
                consumer.commit(asynchronous=False)

    except KeyboardInterrupt:
        logger.info("Kafka consumer: KeyboardInterrupt received, stopping")
    finally:
        consumer.close()
        logger.info("Kafka consumer stopped")
