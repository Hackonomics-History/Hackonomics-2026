"""Tests for RequestIDMiddleware."""
import uuid
from unittest.mock import MagicMock

import pytest

from common.middleware.request_id import RequestIDMiddleware


def _make_request(x_request_id: str | None = None) -> MagicMock:
    request = MagicMock()
    request.META = {}
    if x_request_id is not None:
        request.META["HTTP_X_REQUEST_ID"] = x_request_id
    return request


class TestRequestIDMiddleware:
    def setup_method(self):
        self.response = MagicMock()
        self.get_response = MagicMock(return_value=self.response)
        self.middleware = RequestIDMiddleware(self.get_response)

    def test_generates_uuid_when_header_absent(self):
        request = _make_request()
        self.middleware(request)

        request_id = request.request_id
        assert request_id is not None
        # Validate it's a valid UUID4
        parsed = uuid.UUID(request_id, version=4)
        assert str(parsed) == request_id

    def test_passes_through_upstream_request_id(self):
        request = _make_request(x_request_id="upstream-trace-123")
        self.middleware(request)

        assert request.request_id == "upstream-trace-123"

    def test_echoes_request_id_in_response_header(self):
        request = _make_request(x_request_id="test-id-abc")
        self.middleware(request)

        self.response.__setitem__.assert_called_once_with("X-Request-ID", "test-id-abc")

    def test_generated_id_is_echoed_in_response(self):
        request = _make_request()
        self.middleware(request)

        set_header_call = self.response.__setitem__.call_args
        key, value = set_header_call.args
        assert key == "X-Request-ID"
        assert value == request.request_id

    def test_calls_get_response_exactly_once(self):
        request = _make_request()
        self.middleware(request)

        self.get_response.assert_called_once_with(request)
