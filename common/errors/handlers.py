import logging

import requests as _requests
from rest_framework.response import Response
from rest_framework.views import exception_handler

from common.errors.error_codes import ErrorCode
from common.errors.error_map import ERROR_MAP
from common.errors.exceptions import BusinessException

logger = logging.getLogger(__name__)


def _request_id(context: dict) -> str:
    request = context.get("request")
    if request is None:
        return "-"
    # DRF wraps the WSGI request; request_id is set on the underlying object.
    wsgi = getattr(request, "_request", request)
    return getattr(wsgi, "request_id", "-")


def _log_server_error(exc: Exception, context: dict, status: int) -> None:
    request = context.get("request")
    logger.error(
        "Server error %d [%s %s] request_id=%s exc=%s",
        status,
        getattr(request, "method", "-"),
        getattr(request, "path", "-"),
        _request_id(context),
        type(exc).__name__,
    )


def _make_response(spec: dict, *, request_id: str | None = None) -> Response:
    body: dict = {
        "status": spec["status"],
        "code": spec["code"],
        "message": spec["message"],
    }
    # Include request_id only in 5xx responses — never leak it in 4xx.
    if request_id and request_id != "-" and spec["status"] >= 500:
        body["request_id"] = request_id
    return Response(body, status=spec["status"])


def global_exception_handler(exc, context):
    # ── Typed business exceptions — no logging, these are expected paths ────
    if isinstance(exc, BusinessException):
        spec = ERROR_MAP.get(
            exc.error_code.value,
            ERROR_MAP[ErrorCode.INTERNAL_ERROR.value],
        )
        return _make_response(spec)

    # ── Network timeout → 504 ────────────────────────────────────────────────
    if isinstance(exc, _requests.Timeout):
        spec = ERROR_MAP[ErrorCode.TIMEOUT.value]
        _log_server_error(exc, context, spec["status"])
        return _make_response(spec, request_id=_request_id(context))

    # ── Connection failure → 503 ─────────────────────────────────────────────
    if isinstance(exc, _requests.ConnectionError):
        spec = ERROR_MAP[ErrorCode.SERVICE_UNAVAILABLE.value]
        _log_server_error(exc, context, spec["status"])
        return _make_response(spec, request_id=_request_id(context))

    # ── DRF-handled exceptions (4xx) ─────────────────────────────────────────
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            "status": response.status_code,
            "code": "FrameworkError",
            "message": str(response.data),
        }
        return response

    # ── Unhandled → 500 ──────────────────────────────────────────────────────
    spec = ERROR_MAP[ErrorCode.INTERNAL_ERROR.value]
    _log_server_error(exc, context, spec["status"])
    return _make_response(spec, request_id=_request_id(context))
