import uuid

_INCOMING_HEADER = "HTTP_X_REQUEST_ID"
_OUTGOING_HEADER = "X-Request-ID"


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
        response = self.get_response(request)
        response[_OUTGOING_HEADER] = request.request_id
        return response
