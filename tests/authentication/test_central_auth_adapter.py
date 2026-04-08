"""Tests for CentralAuthAdapter — verifies circuit-breaker and error mapping."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from authentication.adapters.django.auth_service import CentralAuthAdapter
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from common.resilience.circuit_breaker import CircuitOpenError

_ADAPTER_MODULE = "authentication.adapters.django.auth_service"


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@pytest.fixture()
def adapter():
    return CentralAuthAdapter()


@pytest.fixture(autouse=True)
def settings_mock(settings):
    """Provide required settings for all tests in this module."""
    settings.CENTRAL_AUTH_URL = "http://central-auth"
    settings.CENTRAL_AUTH_SERVICE_KEY = "test-service-key"
    settings.CENTRAL_AUTH_TIMEOUT = 5


class TestCentralAuthAdapterLogin:
    def test_returns_json_on_200(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(200, {"access_token": "tok"})
            result = adapter.login("a@b.com", "pass", "dev-1", False)
        assert result == {"access_token": "tok"}

    def test_raises_external_api_failed_on_non_200(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(401)
            with pytest.raises(BusinessException) as exc_info:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_FAILED

    def test_raises_timeout_on_requests_timeout(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.side_effect = requests.Timeout()
            with pytest.raises(BusinessException) as exc_info:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc_info.value.error_code == ErrorCode.TIMEOUT

    def test_raises_service_unavailable_on_connection_error(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.side_effect = requests.ConnectionError()
            with pytest.raises(BusinessException) as exc_info:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc_info.value.error_code == ErrorCode.SERVICE_UNAVAILABLE

    def test_raises_service_unavailable_when_circuit_open(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.side_effect = CircuitOpenError("central_auth")
            with pytest.raises(BusinessException) as exc_info:
                adapter.login("a@b.com", "pass", "dev-1", False)
        assert exc_info.value.error_code == ErrorCode.SERVICE_UNAVAILABLE


class TestCentralAuthAdapterSignup:
    def test_returns_json_on_201(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(201, {"user_id": "u1"})
            result = adapter.signup("a@b.com", "pass")
        assert result == {"user_id": "u1"}

    def test_raises_on_non_2xx(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(500)
            with pytest.raises(BusinessException) as exc_info:
                adapter.signup("a@b.com", "pass")
        assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_FAILED


class TestCentralAuthAdapterRefresh:
    def test_returns_json_on_200(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(200, {"access_token": "new"})
            result = adapter.refresh("refresh-tok")
        assert result == {"access_token": "new"}

    def test_raises_refresh_token_invalid_on_non_200(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(401)
            with pytest.raises(BusinessException) as exc_info:
                adapter.refresh("bad-token")
        assert exc_info.value.error_code == ErrorCode.REFRESH_TOKEN_INVALID


class TestCentralAuthAdapterLogout:
    def test_succeeds_silently_on_200(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(200)
            adapter.logout("refresh-tok")  # no exception

    def test_raises_on_non_200(self, adapter):
        with patch(f"{_ADAPTER_MODULE}._central_auth_http") as mock_http:
            mock_http.return_value = _mock_response(500)
            with pytest.raises(BusinessException) as exc_info:
                adapter.logout("refresh-tok")
        assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_FAILED
