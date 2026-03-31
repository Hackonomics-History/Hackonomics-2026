import functools
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


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
    """
    _open_key = f"cb:{name}:open"
    _failures_key = f"cb:{name}:failures"

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if cache.get(_open_key):
                logger.warning("Circuit OPEN for '%s' — failing fast", name)
                raise CircuitOpenError(name)
            try:
                result = func(*args, **kwargs)
                # Probe or normal call succeeded — reset failure counter.
                cache.delete(_failures_key)
                return result
            except CircuitOpenError:
                # Propagate without double-counting — already open from a nested call.
                raise
            except Exception:
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
                    cache.set(_open_key, 1, timeout=recovery_timeout)
                    cache.delete(_failures_key)
                raise

        return wrapper

    return decorator
