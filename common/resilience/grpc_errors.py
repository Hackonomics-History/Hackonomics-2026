"""gRPC error classification helpers for the circuit breaker and retry stack.

Distinguishes infrastructure failures (should trip the circuit / should retry)
from domain-level errors (should propagate to the caller unchanged).
"""

import grpc


# Status codes that indicate the remote server is down or overloaded.
# These should trip the circuit breaker and be retried.
_INFRASTRUCTURE_CODES = frozenset(
    [
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    ]
)

# Status codes that represent normal domain responses from the server.
# The server was reachable; it returned a structured error.
# These must NOT trip the circuit breaker and must NOT be retried.
_DOMAIN_CODES = frozenset(
    [
        grpc.StatusCode.UNAUTHENTICATED,
        grpc.StatusCode.ALREADY_EXISTS,
        grpc.StatusCode.INVALID_ARGUMENT,
        grpc.StatusCode.NOT_FOUND,
        grpc.StatusCode.PERMISSION_DENIED,
    ]
)


def is_grpc_infrastructure_error(exc: BaseException) -> bool:
    """Return True only when ``exc`` represents a gRPC transport/infrastructure failure.

    Specifically returns True for UNAVAILABLE and DEADLINE_EXCEEDED status codes.
    Returns False for domain errors (UNAUTHENTICATED, ALREADY_EXISTS, etc.) and
    for any non-gRPC exception.

    Parameters
    ----------
    exc:
        The exception to classify.

    Returns
    -------
    bool
        True  → count as failure, may trip circuit, may retry.
        False → domain error, propagate without tripping circuit.
    """
    if not isinstance(exc, grpc.RpcError):
        return False
    try:
        return exc.code() in _INFRASTRUCTURE_CODES
    except Exception:
        # Malformed RpcError — treat conservatively as infrastructure error.
        return True


def is_grpc_retryable(exc: BaseException) -> bool:
    """Return True when the exception is a transient gRPC infrastructure error.

    Alias for ``is_grpc_infrastructure_error`` — used as the tenacity retry
    predicate in ``retry_transient_grpc``.
    """
    return is_grpc_infrastructure_error(exc)
