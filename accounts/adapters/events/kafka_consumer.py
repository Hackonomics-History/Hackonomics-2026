import json
import logging

from confluent_kafka import Consumer, KafkaError
from django.conf import settings
from django.db import transaction

from accounts.application.usecases.event_router import AccountEventRouter

logger = logging.getLogger(__name__)

TOPIC = "user-activities"


def start_kafka_consumer() -> None:
    """Consume events from Kafka with at-least-once delivery semantics.

    Manual offset commit strategy:
      - auto.commit is disabled.
      - The offset is committed ONLY after the DB transaction for the event
        succeeds.  If processing fails the offset is NOT committed, so Kafka
        will redeliver the message on the next poll.
      - AccountEventRouter.route() must be idempotent (skip duplicate event_id).
    """
    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "accounts-service",
            "enable.auto.commit": False,   # manual commit after DB write
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

            try:
                event = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                # Log topic/partition/offset so the raw message can be recovered
                # from Kafka's retention window before committing past it.
                logger.error(
                    "Kafka message decode error: %s | "
                    "topic=%s partition=%d offset=%d — committing to skip unparseable payload",
                    type(exc).__name__,
                    msg.topic(),
                    msg.partition(),
                    msg.offset(),
                )
                consumer.commit(asynchronous=False)
                continue

            try:
                with transaction.atomic():
                    router.route(event)
                # Commit offset only after successful DB write — at-least-once
                consumer.commit(asynchronous=False)
            except Exception as exc:
                logger.error(
                    "Event processing failed (event_id=%s): %s — offset NOT committed",
                    event.get("event_id"),
                    type(exc).__name__,
                )
                # Do not commit; Kafka will redeliver on next poll
    except KeyboardInterrupt:
        logger.info("Kafka consumer: KeyboardInterrupt received, stopping")
    finally:
        consumer.close()
        logger.info("Kafka consumer stopped")
