"""gRPC adapter for the Central-Auth service.

Replaces the HTTP-based ``CentralAuthAdapter`` when ``CENTRAL_AUTH_USE_GRPC=true``.
Implements the same ``AuthServiceAdapter`` Protocol so all callers are unaware
of the transport change.

The gRPC channel is obtained lazily via ``grpc_channel.get_channel()``, which
enforces that ``grpc.experimental.gevent.init_gevent()`` has already run in
the Gunicorn post_fork hook before any call is made.
"""

import logging
import sys
import os

import grpc
from django.conf import settings

from authentication.adapters.django.grpc_channel import get_channel
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from common.middleware.request_id import current_request_id
from common.resilience import (
    CircuitOpenError,
    circuit_breaker,
    is_grpc_infrastructure_error,
    retry_transient_grpc,
)

# Ensure gen/python is on sys.path so the generated stubs can be imported.
_GEN_PYTHON_PATH = os.path.join(
    os.path.dirname(__file__),  # authentication/adapters/django/
    "..",  # authentication/adapters/
    "..",  # authentication/
    "..",  # project root
    "gen",
    "python",
)
_GEN_PYTHON_PATH = os.path.normpath(_GEN_PYTHON_PATH)
if _GEN_PYTHON_PATH not in sys.path:
    sys.path.insert(0, _GEN_PYTHON_PATH)

from auth.v1 import auth_pb2, auth_pb2_grpc  # noqa: E402

logger = logging.getLogger(__name__)


def _build_metadata() -> list[tuple[str, str]]:
    """Build gRPC call metadata injected on every RPC.

    Includes:
    - ``x-service-key``: pre-shared key for service-to-service auth.
    - ``x-request-id``: current request trace ID propagated from
      ``RequestIDMiddleware`` via a ContextVar — empty string when called
      outside a request context (e.g. management commands, Celery tasks).
    """
    metadata = [("x-service-key", settings.CENTRAL_AUTH_SERVICE_KEY)]
    rid = current_request_id.get()
    if rid:
        metadata.append(("x-request-id", rid))
    return metadata


def _grpc_error_to_business(exc: grpc.RpcError, *, context: str) -> BusinessException:
    """Map a gRPC status code to the appropriate ``BusinessException``.

    Infrastructure errors are logged at ERROR level; domain errors at WARNING.
    """
    code = exc.code()
    detail = exc.details() or ""

    _INFRA = {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}
    if code in _INFRA:
        logger.error("[gRPC][%s] infrastructure error code=%s detail=%s", context, code, detail)
    else:
        logger.warning("[gRPC][%s] domain error code=%s detail=%s", context, code, detail)

    mapping = {
        grpc.StatusCode.UNAUTHENTICATED: ErrorCode.INVALID_CREDENTIALS,
        grpc.StatusCode.ALREADY_EXISTS: ErrorCode.DUPLICATE_ENTRY,
        grpc.StatusCode.INVALID_ARGUMENT: ErrorCode.INVALID_PARAMETER,
        grpc.StatusCode.NOT_FOUND: ErrorCode.DATA_NOT_FOUND,
        grpc.StatusCode.UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED: ErrorCode.TIMEOUT,
        grpc.StatusCode.PERMISSION_DENIED: ErrorCode.FORBIDDEN,
    }
    return BusinessException(mapping.get(code, ErrorCode.EXTERNAL_API_FAILED))


def _get_stub() -> auth_pb2_grpc.AuthServiceStub:
    return auth_pb2_grpc.AuthServiceStub(get_channel())


def _timeout() -> int:
    return getattr(settings, "CENTRAL_AUTH_GRPC_TIMEOUT", 5)


@circuit_breaker(
    "central_auth_grpc",
    failure_threshold=5,
    recovery_timeout=30,
    should_trip=is_grpc_infrastructure_error,
)
@retry_transient_grpc(max_attempts=2, wait_seconds=0.3)
def _grpc_login(stub, request, metadata, timeout):
    return stub.Login(request, metadata=metadata, timeout=timeout)


@circuit_breaker(
    "central_auth_grpc",
    failure_threshold=5,
    recovery_timeout=30,
    should_trip=is_grpc_infrastructure_error,
)
@retry_transient_grpc(max_attempts=2, wait_seconds=0.3)
def _grpc_signup(stub, request, metadata, timeout):
    return stub.Signup(request, metadata=metadata, timeout=timeout)


@circuit_breaker(
    "central_auth_grpc",
    failure_threshold=5,
    recovery_timeout=30,
    should_trip=is_grpc_infrastructure_error,
)
@retry_transient_grpc(max_attempts=2, wait_seconds=0.3)
def _grpc_google_login(stub, request, metadata, timeout):
    return stub.GoogleLogin(request, metadata=metadata, timeout=timeout)


@circuit_breaker(
    "central_auth_grpc",
    failure_threshold=5,
    recovery_timeout=30,
    should_trip=is_grpc_infrastructure_error,
)
@retry_transient_grpc(max_attempts=2, wait_seconds=0.3)
def _grpc_refresh(stub, request, metadata, timeout):
    return stub.Refresh(request, metadata=metadata, timeout=timeout)


@circuit_breaker(
    "central_auth_grpc",
    failure_threshold=5,
    recovery_timeout=30,
    should_trip=is_grpc_infrastructure_error,
)
@retry_transient_grpc(max_attempts=2, wait_seconds=0.3)
def _grpc_logout(stub, request, metadata, timeout):
    return stub.Logout(request, metadata=metadata, timeout=timeout)


class GrpcAuthAdapter:
    """gRPC adapter satisfying the ``AuthServiceAdapter`` Protocol.

    All five methods delegate to the Go ``auth.v1.AuthService`` over gRPC.
    The circuit breaker and retry stack are applied at the module-function level
    (not on instance methods) so they share state across adapter instances.
    """

    def login(self, email: str, password: str, device_id: str, remember_me: bool) -> dict:
        stub = _get_stub()
        req = auth_pb2.LoginRequest(
            method=auth_pb2.LOGIN_METHOD_PASSWORD,
            email=email,
            password=password,
            device_id=device_id,
            remember_me=remember_me,
        )
        try:
            resp = _grpc_login(stub, req, _build_metadata(), _timeout())
        except CircuitOpenError:
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
        except grpc.RpcError as exc:
            raise _grpc_error_to_business(exc, context="login")
        return {"access_token": resp.access_token, "refresh_token": resp.refresh_token}

    def signup(self, email: str, password: str) -> dict:
        stub = _get_stub()
        req = auth_pb2.SignupRequest(email=email, password=password)
        try:
            resp = _grpc_signup(stub, req, _build_metadata(), _timeout())
        except CircuitOpenError:
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
        except grpc.RpcError as exc:
            raise _grpc_error_to_business(exc, context="signup")
        return {"ory_id": resp.ory_id, "email": resp.email}

    def google_login(self, email: str, device_id: str) -> dict:
        stub = _get_stub()
        req = auth_pb2.GoogleLoginRequest(email=email, device_id=device_id)
        try:
            resp = _grpc_google_login(stub, req, _build_metadata(), _timeout())
        except CircuitOpenError:
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
        except grpc.RpcError as exc:
            raise _grpc_error_to_business(exc, context="google_login")
        return {"access_token": resp.access_token, "refresh_token": resp.refresh_token}

    def refresh(self, refresh_token: str) -> dict:
        stub = _get_stub()
        req = auth_pb2.RefreshRequest(refresh_token=refresh_token)
        try:
            resp = _grpc_refresh(stub, req, _build_metadata(), _timeout())
        except CircuitOpenError:
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
        except grpc.RpcError as exc:
            # Refresh errors are always token-related — override the default mapping.
            if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise BusinessException(ErrorCode.REFRESH_TOKEN_INVALID)
            raise _grpc_error_to_business(exc, context="refresh")
        return {"access_token": resp.access_token, "refresh_token": resp.refresh_token}

    def logout(self, refresh_token: str) -> None:
        stub = _get_stub()
        req = auth_pb2.LogoutRequest(refresh_token=refresh_token)
        try:
            _grpc_logout(stub, req, _build_metadata(), _timeout())
        except CircuitOpenError:
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
        except grpc.RpcError as exc:
            raise _grpc_error_to_business(exc, context="logout")
