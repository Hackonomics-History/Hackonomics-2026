"""
L1 in-process blacklist cache for the Django service.

Backed by Django's cache framework (Redis in production).
Each entry has a 60-second TTL: long enough to absorb Kafka fan-out latency,
short enough to limit the exposure window after an unblock.

Key patterns:
  blacklist:USER:{kratos_id}        — blocked Kratos identity (JWT sub)
  blacklist:JTI:{jti}               — blocked JWT token ID
  blacklist:SERVICE_KEY:{key_value} — blocked service-to-service key

All functions are safe to call before Django is fully initialised because
they only touch the cache framework, not models or ORM.
"""
from django.core.cache import cache

_BLACKLIST_TTL = 60  # seconds — 1-minute window matches spec
_PREFIX = "blacklist"


def _key(target_type: str, target_value: str) -> str:
    return f"{_PREFIX}:{target_type}:{target_value}"


def is_blacklisted(target_type: str, target_value: str) -> bool:
    """Return True when the target is currently in the blacklist cache."""
    return cache.get(_key(target_type, target_value)) is not None


def set_blacklisted(target_type: str, target_value: str, ttl: int = _BLACKLIST_TTL) -> None:
    """Mark a target as blacklisted in the cache with the given TTL."""
    cache.set(_key(target_type, target_value), 1, timeout=ttl)


def evict(target_type: str, target_value: str) -> None:
    """Remove a target from the blacklist cache (called on unblock events)."""
    cache.delete(_key(target_type, target_value))
