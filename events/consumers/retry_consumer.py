"""Generic Kafka retry consumer with time-delayed re-processing.

Each retry tier is represented by a ``RetryConsumer`` instance parameterised
by ``topic``, ``group_id``, and ``delay_ms``.  The delay is enforced via the
``retry_not_before`` header written by ``retry_router.publish_to_retry()``.

Delay enforcement
-----------------
When a message's ``retry_not_before`` timestamp has not yet elapsed, the
consumer seeks back to that message's offset and sleeps briefly before
re-polling.  This avoids committing past a message that is not yet ready,
while also not blocking the entire process with a long sleep.

At-least-once semantics are preserved:
  - Offset committed only after successful processing OR after routing
    to the next retry tier / DLT.
  - Seek-back on not-yet-ready messages means the offset is never advanced
    prematurely.
"""
import json
import logging
import signal
import time

from confluent_kafka import Consumer, KafkaError, TopicPartition
from django.conf import settings
from django.db import transaction

from accounts.application.usecases.event_router import AccountEventRouter
from events.infra.kafka.retry_router import publish_to_retry

logger = logging.getLogger(__name__)

# Maximum seconds to sleep while waiting for a message's retry delay.
_MAX_SLEEP_S = 5.0


class RetryConsumer:
    """Time-delayed Kafka retry consumer for a single retry tier.

    Args:
        topic:     Kafka topic to consume (e.g. ``user-activities.retry-1``).
        group_id:  Consumer group ID — must be unique per tier.
        delay_ms:  Minimum delay in milliseconds before a message may be
                   processed.  Used only as a fallback when the
                   ``retry_not_before`` header is absent.
    """

    def __init__(self, topic: str, group_id: str, delay_ms: int) -> None:
        self.topic = topic
        self.group_id = group_id
        self.delay_ms = delay_ms
        self._running = True
        signal.signal(signal.SIGTERM, self._on_shutdown)
        signal.signal(signal.SIGINT, self._on_shutdown)

    def _on_shutdown(self, sig, frame) -> None:
        self._running = False
        logger.info(
            "RetryConsumer(%s): shutdown signal received, stopping after current message",
            self.topic,
        )

    def _not_before_ms(self, msg) -> int:
        """Return the retry_not_before header value, falling back to now + delay_ms."""
        for key, value in (msg.headers() or []):
            if key == "retry_not_before":
                try:
                    return int(value.decode())
                except (ValueError, UnicodeDecodeError):
                    pass
        return int(time.time() * 1000) + self.delay_ms

    def _attempt(self, msg) -> int:
        for key, value in (msg.headers() or []):
            if key == "retry_attempt":
                try:
                    return int(value.decode())
                except (ValueError, UnicodeDecodeError):
                    return 0
        return 0

    def run(self) -> None:
        consumer = Consumer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": self.group_id,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([self.topic])
        router = AccountEventRouter()
        logger.info(
            "RetryConsumer started (topic=%s group=%s delay_ms=%d)",
            self.topic,
            self.group_id,
            self.delay_ms,
        )

        try:
            while self._running:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error(
                        "RetryConsumer(%s) error: %s", self.topic, msg.error()
                    )
                    continue

                # ── Delay check ─────────────────────────────────────────────
                not_before_ms = self._not_before_ms(msg)
                now_ms = int(time.time() * 1000)
                if now_ms < not_before_ms:
                    remaining_s = (not_before_ms - now_ms) / 1000
                    # Seek back so this message is re-polled after the sleep.
                    consumer.seek(
                        TopicPartition(msg.topic(), msg.partition(), msg.offset())
                    )
                    time.sleep(min(remaining_s, _MAX_SLEEP_S))
                    continue

                # ── Decode ──────────────────────────────────────────────────
                try:
                    event = json.loads(msg.value().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.error(
                        "RetryConsumer(%s) decode error: %s offset=%d — routing to DLT",
                        self.topic,
                        type(exc).__name__,
                        msg.offset(),
                    )
                    publish_to_retry(msg.value(), msg.headers(), attempt=3)
                    consumer.commit(asynchronous=False)
                    continue

                # ── Process ─────────────────────────────────────────────────
                attempt = self._attempt(msg)
                try:
                    with transaction.atomic():
                        router.route(event)
                    consumer.commit(asynchronous=False)
                    logger.info(
                        "RetryConsumer(%s) processed event_id=%s (attempt=%d)",
                        self.topic,
                        event.get("event_id"),
                        attempt,
                    )

                except Exception as exc:
                    logger.error(
                        "RetryConsumer(%s) processing failed (event_id=%s attempt=%d): %s",
                        self.topic,
                        event.get("event_id"),
                        attempt,
                        type(exc).__name__,
                    )
                    publish_to_retry(msg.value(), msg.headers(), attempt + 1)
                    consumer.commit(asynchronous=False)

        except KeyboardInterrupt:
            logger.info("RetryConsumer(%s): KeyboardInterrupt, stopping", self.topic)
        finally:
            consumer.close()
            logger.info("RetryConsumer(%s) stopped", self.topic)
