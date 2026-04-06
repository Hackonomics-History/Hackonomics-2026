import uuid
from contextvars import ContextVar

_INCOMING_HEADER = "HTTP_X_REQUEST_ID"
_OUTGOING_HEADER = "X-Request-ID"

# Greenlet-safe ContextVar so adapters in the service layer can read the current
# request ID without receiving a Django ``request`` object.
# Set by RequestIDMiddleware.__call__ at the start of every request.
current_request_id: ContextVar[str] = ContextVar("current_request_id", default="")


class RequestIDMiddleware:
    """Attach a traceable request ID to every request/response cycle.

    Reads ``X-Request-ID`` from the incoming request headers (typically set by
    an upstream load balancer or API gateway). Generates a UUID4 when absent.

    The value is stored on ``request.request_id`` so it is accessible in views,
    middleware, and the global exception handler for structured log output.

    The same ID is echoed in the ``X-Request-ID`` response header so clients
    can correlate their requests with server-side logs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.META.get(_INCOMING_HEADER) or str(uuid.uuid4())
        current_request_id.set(request.request_id)
        response = self.get_response(request)
        response[_OUTGOING_HEADER] = request.request_id
        return response
