import requests
import tenacity


def retry_transient(max_attempts: int = 2, wait_seconds: float = 0.3):
    """Retry decorator scoped to transient network errors only.

    Retries on: ``requests.Timeout``, ``requests.ConnectionError``.
    Does NOT retry on: HTTP error responses, ``CircuitOpenError``,
    ``BusinessException``, or any other application-level exception.

    Exponential backoff with jitter is applied between attempts.

    Args:
        max_attempts:  Total call attempts including the first (default 2 = 1 retry).
        wait_seconds:  Base wait multiplier in seconds; grows exponentially up to 2s.
    """
    return tenacity.retry(
        retry=tenacity.retry_if_exception_type(
            (requests.Timeout, requests.ConnectionError)
        ),
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential(
            multiplier=wait_seconds,
            min=wait_seconds,
            max=2.0,
        ),
        reraise=True,
    )


def retry_transient_grpc(max_attempts: int = 2, wait_seconds: float = 0.3):
    """Retry decorator scoped to transient gRPC infrastructure errors only.

    Retries on: ``grpc.StatusCode.UNAVAILABLE``, ``grpc.StatusCode.DEADLINE_EXCEEDED``.
    Does NOT retry on: domain errors (UNAUTHENTICATED, ALREADY_EXISTS, INVALID_ARGUMENT),
    ``CircuitOpenError``, ``BusinessException``, or any non-gRPC exception.

    Use this in place of ``retry_transient`` when wrapping gRPC calls.  Pair it
    with a circuit breaker that has ``should_trip=is_grpc_infrastructure_error``
    so domain errors do not trip the circuit.

    Args:
        max_attempts:  Total call attempts including the first (default 2 = 1 retry).
        wait_seconds:  Base wait multiplier in seconds; grows exponentially up to 2s.
    """
    from common.resilience.grpc_errors import is_grpc_retryable  # noqa: PLC0415

    return tenacity.retry(
        retry=tenacity.retry_if_exception(is_grpc_retryable),
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential(
            multiplier=wait_seconds,
            min=wait_seconds,
            max=2.0,
        ),
        reraise=True,
    )
