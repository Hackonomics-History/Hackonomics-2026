import functools
import logging
import random

import sentry_sdk
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _sentry_capture_circuit_open(name: str, failures: int, window: int) -> None:
    """Send a fatal Sentry exception event when a circuit trips to OPEN.

    Uses ``capture_exception`` inside a try/except so that Sentry attaches
    a real Python stack trace to the event.  ``capture_message`` without an
    active exception context does not include a stack trace; using a synthetic
    raise/catch ensures the "Exceptions" tab in Sentry has a full traceback,
    which is essential for pinpointing the call site that tripped the breaker.
    """
    try:
        raise RuntimeError(
            f"[REDIS_DOWN_CIRCUIT_OPEN] Circuit breaker OPEN for '{name}' "
            f"({failures} failures in {window}s)"
        )
    except RuntimeError:
        with sentry_sdk.push_scope() as scope:
            scope.set_level("fatal")
            scope.set_tag("circuit_state", "OPEN")
            scope.set_tag("alert_id", "REDIS_DOWN_CIRCUIT_OPEN")
            scope.set_tag("failed_service", name)
            scope.set_extra("failure_count", failures)
            scope.set_extra("failure_window_seconds", window)
            sentry_sdk.capture_exception()


def _sentry_capture_circuit_half_open(name: str) -> None:
    """Send a warning Sentry exception event when a circuit enters HALF-OPEN.

    Uses the same try/except pattern as ``_sentry_capture_circuit_open`` so
    that a stack trace is always attached.  Called once per probe attempt so
    the on-call engineer can track recovery progress without flooding quota.
    """
    try:
        raise RuntimeError(
            f"[REDIS_CB_HALF_OPEN] Circuit breaker HALF-OPEN probe for '{name}'"
        )
    except RuntimeError:
        with sentry_sdk.push_scope() as scope:
            scope.set_level("warning")
            scope.set_tag("circuit_state", "HALF_OPEN")
            scope.set_tag("failed_service", name)
            sentry_sdk.capture_exception()


def _jittered_timeout(base: int, jitter_pct: int = 15) -> int:
    """Return base ± (base * jitter_pct%) random offset.

    Prevents thundering-herd: when many Gunicorn workers share a Redis-backed
    circuit breaker, all workers would probe at the exact same instant if the
    recovery_timeout were fixed. A ±15% jitter spreads probes over a short
    window so the upstream service sees gradual ramp-up instead of a spike.
    """
    jitter_range = int(base * jitter_pct / 100)
    if jitter_range == 0:
        return base
    return max(1, base + random.randint(-jitter_range, jitter_range))


class CircuitOpenError(Exception):
    """Raised immediately when a circuit breaker is in the OPEN state."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        super().__init__(f"Circuit open for service: {service_name}")


def circuit_breaker(
    name: str,
    *,
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
    failure_window: int = 60,
    should_trip=None,
):
    """Redis-backed distributed circuit breaker decorator.

    States
    ------
    CLOSED   — Normal operation. Failures are counted in a sliding window.
    OPEN     — All calls fail immediately for `recovery_timeout` seconds.
    HALF_OPEN — Implicit: the first call after recovery is treated as a probe.
                Success → CLOSED (failure counter cleared).
                Failure → OPEN again for another `recovery_timeout` seconds.

    Redis keys
    ----------
    ``cb:{name}:failures`` — INCR counter with TTL = failure_window.
    ``cb:{name}:open``     — Presence flag with TTL = recovery_timeout.

    Args:
        name:              Unique service identifier (used as Redis key prefix).
        failure_threshold: Failures within ``failure_window`` seconds before opening.
        recovery_timeout:  Seconds the circuit stays OPEN before allowing a probe.
        failure_window:    Sliding window in seconds for counting failures.
        should_trip:       Optional callable ``(exc: Exception) -> bool``.
                           When provided, an exception is only counted as a circuit
                           failure when ``should_trip(exc)`` returns ``True``.
                           When it returns ``False`` the exception is re-raised
                           immediately without touching the failure counter — useful
                           for distinguishing gRPC domain errors (UNAUTHENTICATED,
                           ALREADY_EXISTS) from infrastructure failures (UNAVAILABLE).
                           When ``None`` (default), all exceptions count as failures,
                           preserving the original behaviour.
    """
    _open_key = f"cb:{name}:open"
    _failures_key = f"cb:{name}:failures"
    # _probe_key persists for (recovery_timeout + 10)s so the HALF-OPEN window is
    # detectable even after _open_key expires (TTL = recovery_timeout).
    _probe_key = f"cb:{name}:probe"

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if cache.get(_open_key):
                logger.warning("Circuit OPEN for '%s' — failing fast", name)
                raise CircuitOpenError(name)

            # _open_key expired but _probe_key still alive → HALF-OPEN probe.
            if cache.get(_probe_key):
                logger.info("Circuit HALF-OPEN probe for '%s'", name)
                _sentry_capture_circuit_half_open(name)

            try:
                result = func(*args, **kwargs)
                # Probe or normal call succeeded — reset failure counter and probe key.
                cache.delete(_failures_key)
                cache.delete(_probe_key)
                return result
            except CircuitOpenError:
                # Propagate without double-counting — already open from a nested call.
                raise
            except Exception as exc:
                # If a classifier is provided and says "don't trip", propagate the
                # exception as a domain error without touching the failure counter.
                if should_trip is not None and not should_trip(exc):
                    raise
                # Sliding-window counter: set TTL only on first entry, then INCR.
                cache.add(_failures_key, 0, timeout=failure_window)
                failures = cache.incr(_failures_key)
                if failures >= failure_threshold:
                    logger.error(
                        "Circuit OPENING for '%s' after %d failures in %ds window",
                        name,
                        failures,
                        failure_window,
                    )
                    jittered = _jittered_timeout(recovery_timeout)
                    cache.set(_open_key, 1, timeout=jittered)
                    # Probe key outlives open key so HALF-OPEN state is observable.
                    cache.set(_probe_key, 1, timeout=jittered + 10)
                    cache.delete(_failures_key)
                    _sentry_capture_circuit_open(name, failures, failure_window)
                raise

        return wrapper

    return decorator
