import re
import uuid
from contextvars import ContextVar

_INCOMING_HEADER = "HTTP_X_REQUEST_ID"
_OUTGOING_HEADER = "X-Request-ID"

# Only accept header values that look like safe trace IDs (alphanumeric + - _).
# Reject anything else and generate a fresh UUID so attacker-controlled strings
# never reach Kafka messages, log fields, or downstream ContextVar consumers.
_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

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
        raw = request.META.get(_INCOMING_HEADER, "")
        request.request_id = raw if _REQUEST_ID_RE.match(raw) else str(uuid.uuid4())
        current_request_id.set(request.request_id)
        response = self.get_response(request)
        response[_OUTGOING_HEADER] = request.request_id
        return response
