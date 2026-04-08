"""Retry routing utility — routes failed Kafka messages to the correct retry tier.

Retry topology for the user-activities stream:

  user-activities (main)
      │  failure, attempt 0 → 1
      ▼
  user-activities.retry-1   delay: 60 s
      │  failure, attempt 1 → 2
      ▼
  user-activities.retry-2   delay: 300 s
      │  failure, attempt 2 → 3
      ▼
  user-activities.dlt        no delay — manual inspection only

Decode errors on the main topic skip retries and go directly to the DLT
(attempt ≥ 3) because a malformed payload will never recover.

Headers added/updated on every routed message
----------------------------------------------
retry_attempt     — attempt number at the TARGET topic (str-encoded int bytes)
retry_not_before  — Unix ms timestamp; consumer must not process before this time
"""
import logging
import time

from events.infra.kafka.producer import KafkaEventProducer

logger = logging.getLogger(__name__)

TOPIC_RETRY_1 = "user-activities.retry-1"
TOPIC_RETRY_2 = "user-activities.retry-2"
TOPIC_DLT = "user-activities.dlt"

# Minimum delay before a retry consumer may process the message.
_DELAY_MS: dict[int, int] = {
    1: 60_000,   # retry-1: 1 minute
    2: 300_000,  # retry-2: 5 minutes
}


def _target(attempt: int) -> tuple[str, int]:
    """Return (topic, delay_ms) for the given attempt number."""
    if attempt == 1:
        return TOPIC_RETRY_1, _DELAY_MS[1]
    if attempt == 2:
        return TOPIC_RETRY_2, _DELAY_MS[2]
    return TOPIC_DLT, 0


def publish_to_retry(
    event_bytes: bytes,
    original_headers: list[tuple[str, bytes]] | None,
    attempt: int,
) -> bool:
    """Route a failed message to the appropriate retry topic or DLT.

    Args:
        event_bytes:       Raw message bytes — forwarded unchanged.
        original_headers:  Headers from the source message (confluent_kafka format).
        attempt:           Attempt number at the DESTINATION topic.
                           Pass ``attempt + 1`` relative to the current consumer.
                           Pass ``3`` to send directly to the DLT.

    Returns True if the message was successfully delivered.
    """
    target_topic, delay_ms = _target(attempt)
    retry_not_before_ms = int(time.time() * 1000) + delay_ms

    # Rebuild header dict, dropping any stale retry headers from upstream.
    headers: dict[str, bytes] = {
        key: value
        for key, value in (original_headers or [])
        if key not in ("retry_attempt", "retry_not_before")
    }
    headers["retry_attempt"] = str(attempt).encode()
    headers["retry_not_before"] = str(retry_not_before_ms).encode()

    delivered = KafkaEventProducer().publish_raw(
        target_topic,
        event_bytes,
        list(headers.items()),
    )

    if delivered:
        logger.info(
            "Routed to %s (attempt=%d not_before=%d)",
            target_topic,
            attempt,
            retry_not_before_ms,
        )
    else:
        logger.error(
            "Failed to route to %s (attempt=%d) — message may be lost",
            target_topic,
            attempt,
        )

    return delivered
