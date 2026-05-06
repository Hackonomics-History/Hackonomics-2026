"""
Kafka consumer for the blacklist-sync topic.

Consumes BlacklistSyncEvents published by Central-auth's AdminBlacklistService
and maintains the Django-side L1 blacklist cache (60-second TTL per entry).

Event types:
  blacklist.sync    → set_blacklisted(target_type, target_value)
  blacklist.unblock → evict(target_type, target_value)

Consumer group: hackonomics-blacklist-sync
  All Django instances join the same group so each event is processed exactly
  once per group. Django's L1 cache is backed by Redis, so any instance that
  processes the event updates the shared Redis cache; all other instances pick
  up the entry on their next L1 lookup.

Offset policy: earliest — on first start (no committed offset) the consumer
  replays the entire topic, ensuring newly deployed instances inherit the full
  blacklist state without a separate warm-up call.
"""
import json
import logging

from confluent_kafka import Consumer, KafkaError
from django.conf import settings

from authentication.adapters.django import blacklist_cache

logger = logging.getLogger(__name__)

TOPIC = "blacklist-sync"
GROUP_ID = "hackonomics-blacklist-sync"

_VALID_TARGET_TYPES = {"USER", "JTI", "SERVICE_KEY"}
_MAX_TARGET_VALUE_LEN = 512


def _mask(target_type: str, value: str) -> str:
    """Return a safe-to-log representation of a target value.

    SERVICE_KEY values are credential material — log only the first 8 characters.
    All other types (USER UUID, JTI) are logged in full.
    """
    if target_type == "SERVICE_KEY":
        return value[:8] + "…"
    return value


def start_blacklist_sync_consumer() -> None:
    """Blocking loop: consume BlacklistSyncEvents and maintain the L1 blacklist cache.

    Delivery semantics
    ------------------
    - auto.commit is disabled; offsets are committed manually after each outcome.
    - Processing success   → commit offset, continue.
    - Decode error         → log and commit (malformed payloads are permanent failures).
    - Missing fields       → log warning and commit (no retry needed; payload is unusable).
    """
    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": GROUP_ID,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("Blacklist sync consumer started (topic=%s, group=%s)", TOPIC, GROUP_ID)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Blacklist sync consumer error: %s", msg.error())
                continue

            # ── Decode ──────────────────────────────────────────────────────
            try:
                event = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.error(
                    "Blacklist sync decode error: %s | topic=%s partition=%d offset=%d",
                    type(exc).__name__,
                    msg.topic(),
                    msg.partition(),
                    msg.offset(),
                )
                consumer.commit(asynchronous=False)
                continue

            # ── Validate ─────────────────────────────────────────────────────
            event_type = event.get("event_type", "")
            target_type = event.get("target_type", "")
            target_value = event.get("target_value", "")

            if not target_type or not target_value:
                logger.warning(
                    "Blacklist sync event missing required fields (event_type=%s) — skipping",
                    event_type,
                )
                consumer.commit(asynchronous=False)
                continue

            if target_type not in _VALID_TARGET_TYPES:
                logger.error(
                    "Blacklist sync: unknown target_type=%r — discarding event",
                    target_type,
                )
                consumer.commit(asynchronous=False)
                continue

            if len(target_value) > _MAX_TARGET_VALUE_LEN:
                logger.error(
                    "Blacklist sync: target_value exceeds max length (%d) for type=%s — discarding",
                    _MAX_TARGET_VALUE_LEN,
                    target_type,
                )
                consumer.commit(asynchronous=False)
                continue

            # ── Apply ─────────────────────────────────────────────────────────
            if event_type == "blacklist.sync":
                blacklist_cache.set_blacklisted(target_type, target_value)
                logger.info(
                    "L1 blacklist updated: %s/%s blocked",
                    target_type,
                    _mask(target_type, target_value),
                )
            elif event_type == "blacklist.unblock":
                blacklist_cache.evict(target_type, target_value)
                logger.info(
                    "L1 blacklist updated: %s/%s unblocked",
                    target_type,
                    _mask(target_type, target_value),
                )
            else:
                logger.debug(
                    "Blacklist sync: unknown event_type=%s — skipping",
                    event_type,
                )

            consumer.commit(asynchronous=False)

    except KeyboardInterrupt:
        logger.info("Blacklist sync consumer: KeyboardInterrupt received, stopping")
    finally:
        consumer.close()
        logger.info("Blacklist sync consumer stopped")
