"""Tests for GrpcAuthAdapter — verifies gRPC stub delegation and error mapping."""
import sys
import os
from unittest.mock import MagicMock, patch

import grpc
import pytest

# Ensure gen/python is importable in the test environment.
_GEN_PYTHON = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "gen", "python")
)
if _GEN_PYTHON not in sys.path:
    sys.path.insert(0, _GEN_PYTHON)

from auth.v1 import auth_pb2

from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from common.resilience.circuit_breaker import CircuitOpenError
from tests.conftest import FakeRpcError

_ADAPTER_MODULE = "authentication.adapters.django.grpc_auth_service"


def _rpc_error(code: grpc.StatusCode, detail: str = "") -> grpc.RpcError:
    return FakeRpcError(code, detail)


def _login_response(**kwargs) -> MagicMock:
    resp = MagicMock(spec=auth_pb2.LoginResponse)
    resp.access_token = kwargs.get("access_token", "acc")
    resp.refresh_token = kwargs.get("refresh_token", "ref")
    return resp


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.CENTRAL_AUTH_SERVICE_KEY = "test-key"
    settings.CENTRAL_AUTH_GRPC_TARGET = "auth-server:50051"
    settings.CENTRAL_AUTH_GRPC_TIMEOUT = 5
    settings.CENTRAL_AUTH_USE_GRPC = True


@pytest.fixture()
def adapter():
    from authentication.adapters.django.grpc_auth_service import GrpcAuthAdapter
    return GrpcAuthAdapter()


@pytest.fixture(autouse=True)
def _patch_channel():
    """Replace get_channel with a MagicMock so no real gRPC channel is created."""
    with patch(f"{_ADAPTER_MODULE}.get_channel") as mock:
        mock.return_value = MagicMock()
        yield mock


class TestGrpcAuthAdapterLogin:
    def test_happy_path_returns_tokens(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_login") as mock_call:
            mock_call.return_value = _login_response(access_token="at", refresh_token="rt")
            result = adapter.login("a@b.com", "pass", "dev-1", False)
        assert result == {"access_token": "at", "refresh_token": "rt"}

    def test_unavailable_raises_service_unavailable(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_login") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.UNAVAILABLE)
            with pytest.raises(BusinessException) as exc:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc.value.error_code == ErrorCode.SERVICE_UNAVAILABLE

    def test_deadline_exceeded_raises_timeout(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_login") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED)
            with pytest.raises(BusinessException) as exc:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc.value.error_code == ErrorCode.TIMEOUT

    def test_unauthenticated_raises_invalid_credentials(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_login") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.UNAUTHENTICATED)
            with pytest.raises(BusinessException) as exc:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc.value.error_code == ErrorCode.INVALID_CREDENTIALS

    def test_circuit_open_raises_service_unavailable(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_login") as mock_call:
            mock_call.side_effect = CircuitOpenError("central_auth_grpc")
            with pytest.raises(BusinessException) as exc:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc.value.error_code == ErrorCode.SERVICE_UNAVAILABLE

    def test_metadata_includes_service_key(self, adapter, settings):
        captured = {}
        def capture_call(stub, req, metadata, timeout):
            captured["metadata"] = dict(metadata)
            return _login_response()
        with patch(f"{_ADAPTER_MODULE}._grpc_login", side_effect=capture_call):
            adapter.login("a@b.com", "pass", "dev-1", False)
        assert captured["metadata"].get("x-service-key") == settings.CENTRAL_AUTH_SERVICE_KEY


class TestGrpcAuthAdapterSignup:
    def test_happy_path_returns_ory_id_and_email(self, adapter):
        resp = MagicMock()
        resp.ory_id = "kratos-uuid"
        resp.email = "a@b.com"
        with patch(f"{_ADAPTER_MODULE}._grpc_signup") as mock_call:
            mock_call.return_value = resp
            result = adapter.signup("a@b.com", "pass")
        assert result == {"ory_id": "kratos-uuid", "email": "a@b.com"}

    def test_already_exists_raises_duplicate_entry(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_signup") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.ALREADY_EXISTS)
            with pytest.raises(BusinessException) as exc:
                adapter.signup("a@b.com", "pass")
        assert exc.value.error_code == ErrorCode.DUPLICATE_ENTRY

    def test_invalid_argument_raises_invalid_parameter(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_signup") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.INVALID_ARGUMENT)
            with pytest.raises(BusinessException) as exc:
                adapter.signup("a@b.com", "pass")
        assert exc.value.error_code == ErrorCode.INVALID_PARAMETER


class TestGrpcAuthAdapterGoogleLogin:
    def test_happy_path_returns_tokens(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_google_login") as mock_call:
            mock_call.return_value = _login_response(access_token="gat", refresh_token="grt")
            result = adapter.google_login("a@b.com", "dev-google")
        assert result == {"access_token": "gat", "refresh_token": "grt"}

    def test_unauthenticated_maps_to_invalid_credentials(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_google_login") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.UNAUTHENTICATED)
            with pytest.raises(BusinessException) as exc:
                adapter.google_login("a@b.com", "dev-google")
        assert exc.value.error_code == ErrorCode.INVALID_CREDENTIALS


class TestGrpcAuthAdapterRefresh:
    def test_happy_path_returns_new_tokens(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_refresh") as mock_call:
            mock_call.return_value = _login_response(access_token="new_at", refresh_token="new_rt")
            result = adapter.refresh("old_refresh")
        assert result == {"access_token": "new_at", "refresh_token": "new_rt"}

    def test_unauthenticated_maps_to_refresh_token_invalid(self, adapter):
        """For refresh, UNAUTHENTICATED maps to REFRESH_TOKEN_INVALID (not INVALID_CREDENTIALS)."""
        with patch(f"{_ADAPTER_MODULE}._grpc_refresh") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.UNAUTHENTICATED)
            with pytest.raises(BusinessException) as exc:
                adapter.refresh("bad_token")
        assert exc.value.error_code == ErrorCode.REFRESH_TOKEN_INVALID


class TestGrpcAuthAdapterLogout:
    def test_happy_path_returns_none(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_logout") as mock_call:
            mock_call.return_value = MagicMock()
            result = adapter.logout("refresh_tok")
        assert result is None

    def test_unavailable_raises_service_unavailable(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._grpc_logout") as mock_call:
            mock_call.side_effect = _rpc_error(grpc.StatusCode.UNAVAILABLE)
            with pytest.raises(BusinessException) as exc:
                adapter.logout("refresh_tok")
        assert exc.value.error_code == ErrorCode.SERVICE_UNAVAILABLE


class TestGrpcMetadataPropagation:
    def test_request_id_included_when_set(self, adapter):
        from common.middleware.request_id import current_request_id

        token = current_request_id.set("trace-abc-123")
        try:
            captured = {}
            def capture_call(stub, req, metadata, timeout):
                captured["metadata"] = dict(metadata)
                return _login_response()
            with patch(f"{_ADAPTER_MODULE}._grpc_login", side_effect=capture_call):
                adapter.login("a@b.com", "pass", "dev-1", False)
            assert captured["metadata"].get("x-request-id") == "trace-abc-123"
        finally:
            current_request_id.reset(token)

    def test_request_id_omitted_when_empty(self, adapter):
        from common.middleware.request_id import current_request_id

        token = current_request_id.set("")
        try:
            captured = {}
            def capture_call(stub, req, metadata, timeout):
                captured["metadata"] = dict(metadata)
                return _login_response()
            with patch(f"{_ADAPTER_MODULE}._grpc_login", side_effect=capture_call):
                adapter.login("a@b.com", "pass", "dev-1", False)
            assert "x-request-id" not in captured["metadata"]
        finally:
            current_request_id.reset(token)
