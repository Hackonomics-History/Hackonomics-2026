"""Resilient Celery Beat scheduler with Redis health monitoring and Sentry alerts.

Architecture
------------
``ResilientBeatScheduler`` extends ``django_celery_beat.schedulers.DatabaseScheduler``
so the schedule is always stored in PostgreSQL — independent of Redis availability.
On top of that, it monitors whether the Redis *broker* is reachable:

* 5 consecutive broker-ping failures → circuit trips to OPEN; Sentry alert fired.
* After ``RESET_TIMEOUT`` seconds the circuit enters HALF-OPEN and probes Redis.
* On successful probe → CLOSED; Sentry recovery alert fired.

Because scheduling state lives in the DB, Beat continues to determine *when* tasks
should run even while Redis is down. Tasks cannot be *dispatched* until the broker
recovers, but the scheduler never loses its clock or schedule.
"""

import logging
import random
import time
from typing import Optional

import redis as redis_lib
import sentry_sdk
from django.conf import settings

logger = logging.getLogger(__name__)

# ── CB constants ──────────────────────────────────────────────────────────────
_FAILURE_THRESHOLD: int = 5
_RESET_TIMEOUT_BASE: int = 60   # seconds — initial probe interval
_RESET_TIMEOUT_MAX: int = 300   # seconds — cap on exponential back-off
_JITTER_PCT: float = 0.15       # ±15% jitter
_HEALTH_CHECK_INTERVAL: int = 10  # seconds between Redis pings during CLOSED


def _jittered_backoff(base: int, attempt: int) -> float:
    """Exponential backoff with ±JITTER_PCT% jitter, capped at _RESET_TIMEOUT_MAX."""
    raw = min(base * (2 ** attempt), _RESET_TIMEOUT_MAX)
    jitter = raw * _JITTER_PCT
    return raw + random.uniform(-jitter, jitter)


class _BrokerCircuitBreaker:
    """Standalone (non-Redis-backed) CB for the Redis broker itself.

    State is held in process memory. Because Beat runs as a single process,
    in-process state is sufficient and avoids the circular dependency of
    checking Redis health via Redis.
    """

    STATE_CLOSED = "CLOSED"
    STATE_OPEN = "OPEN"
    STATE_HALF_OPEN = "HALF_OPEN"

    def __init__(self) -> None:
        self.state: str = self.STATE_CLOSED
        self._failures: int = 0
        self._open_since: float = 0.0
        self._probe_attempt: int = 0          # counts failed HALF-OPEN probes
        self._next_probe_at: float = 0.0
        self._last_health_check: float = 0.0

    # ── public API ────────────────────────────────────────────────────────────

    def record_success(self) -> None:
        if self.state != self.STATE_CLOSED:
            logger.info("Beat broker circuit → CLOSED (Redis recovered)")
            _sentry_broker_recovered(self._open_since)
        self.state = self.STATE_CLOSED
        self._failures = 0
        self._probe_attempt = 0

    def record_failure(self) -> None:
        if self.state == self.STATE_OPEN:
            return  # already open; don't re-count
        self._failures += 1
        if self._failures >= _FAILURE_THRESHOLD:
            self._trip_open()

    def allow_probe(self) -> bool:
        """Return True when a HALF-OPEN probe attempt is permitted."""
        if self.state == self.STATE_CLOSED:
            return True
        if self.state == self.STATE_OPEN and time.monotonic() >= self._next_probe_at:
            self.state = self.STATE_HALF_OPEN
            return True
        if self.state == self.STATE_HALF_OPEN:
            return True
        return False

    def on_probe_failure(self) -> None:
        """Called when a HALF-OPEN probe fails — extends backoff exponentially."""
        self._probe_attempt += 1
        delay = _jittered_backoff(_RESET_TIMEOUT_BASE, self._probe_attempt)
        self._next_probe_at = time.monotonic() + delay
        self.state = self.STATE_OPEN
        logger.warning(
            "Beat broker probe failed (attempt %d) — next probe in %.0fs",
            self._probe_attempt,
            delay,
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _trip_open(self) -> None:
        self.state = self.STATE_OPEN
        self._open_since = time.time()
        delay = _jittered_backoff(_RESET_TIMEOUT_BASE, 0)
        self._next_probe_at = time.monotonic() + delay
        logger.error(
            "Beat broker circuit → OPEN (%d consecutive failures). Next probe in %.0fs.",
            self._failures,
            delay,
        )
        _sentry_broker_open(self._failures)


# ── Sentry helpers ────────────────────────────────────────────────────────────

def _sentry_broker_open(failures: int) -> None:
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("circuit_state", "OPEN")
        scope.set_tag("alert_id", "REDIS_DOWN_SCHEDULER_FALLBACK_ACTIVE")
        scope.set_tag("failed_service", "django_redis_broker")
        scope.set_extra("failure_count", failures)
        scope.set_extra("scheduler", "ResilientBeatScheduler")
        sentry_sdk.capture_message(
            f"REDIS_DOWN_SCHEDULER_FALLBACK_ACTIVE: Celery Beat broker circuit OPEN after "
            f"{failures} failures — scheduling continues via DatabaseScheduler; dispatch paused.",
            level="fatal",
        )


def _sentry_broker_recovered(open_since: float) -> None:
    downtime = time.time() - open_since
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("circuit_state", "CLOSED")
        scope.set_tag("failed_service", "django_redis_broker")
        scope.set_extra("downtime_seconds", round(downtime, 1))
        scope.set_extra("scheduler", "ResilientBeatScheduler")
        sentry_sdk.capture_message(
            f"Celery Beat broker circuit CLOSED — Redis recovered after {downtime:.0f}s.",
            level="info",
        )


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _make_redis_client() -> redis_lib.Redis:
    """Build a short-timeout Redis client for health pings only."""
    url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    return redis_lib.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)


def _ping_redis(client: redis_lib.Redis) -> bool:
    try:
        return client.ping()
    except Exception:
        return False


try:
    from django_celery_beat.schedulers import DatabaseScheduler as _BaseScheduler
except ImportError:
    # django-celery-beat not installed; fall back to PersistentScheduler so the
    # module can be imported without crashing. Install django-celery-beat.
    from celery.beat import PersistentScheduler as _BaseScheduler  # type: ignore[assignment]
    logger.warning(
        "django-celery-beat not installed. ResilientBeatScheduler falls back to "
        "PersistentScheduler — Redis health monitoring still active."
    )


class ResilientBeatScheduler(_BaseScheduler):  # type: ignore[valid-type,misc]
    """Beat scheduler that monitors Redis broker health and alerts via Sentry.

    Schedule persistence: PostgreSQL (via DatabaseScheduler) — unaffected by Redis.
    Broker monitoring:   In-process circuit breaker pings Redis every 10s.
    Fallback behaviour:  Scheduling continues; dispatch resumes when Redis recovers.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cb = _BrokerCircuitBreaker()
        self._redis_client: Optional[redis_lib.Redis] = None
        try:
            self._redis_client = _make_redis_client()
        except Exception as exc:
            logger.warning("Could not create Redis health-check client: %s", exc)

    # ── override tick to inject health check ──────────────────────────────────

    def tick(self, event_t=None, *args, **kwargs):
        self._maybe_check_broker()
        if event_t is not None:
            return super().tick(event_t, *args, **kwargs)
        return super().tick(*args, **kwargs)

    # ── Redis health monitoring ───────────────────────────────────────────────

    def _maybe_check_broker(self) -> None:
        if self._redis_client is None:
            return
        now = time.monotonic()
        cb = self._cb

        if cb.state == _BrokerCircuitBreaker.STATE_CLOSED:
            if now - cb._last_health_check < _HEALTH_CHECK_INTERVAL:
                return
            cb._last_health_check = now
            if _ping_redis(self._redis_client):
                cb.record_success()
            else:
                cb.record_failure()
                logger.warning(
                    "Beat broker ping failed (%d/%d)",
                    cb._failures,
                    _FAILURE_THRESHOLD,
                )

        elif cb.allow_probe():
            cb._last_health_check = now
            if _ping_redis(self._redis_client):
                cb.record_success()
            else:
                cb.on_probe_failure()
