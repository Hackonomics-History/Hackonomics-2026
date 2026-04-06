"""Tests for the circuit breaker ``should_trip`` parameter.

Existing tests in test_circuit_breaker.py are NOT modified — this file adds
a separate test class so the original behaviour is verified independently.
"""
from unittest.mock import MagicMock, patch

import grpc
import pytest

from common.resilience.circuit_breaker import CircuitOpenError, circuit_breaker
from common.resilience.grpc_errors import is_grpc_infrastructure_error
from tests.conftest import FakeRpcError

_FAILURES_KEY = "cb:grpc_svc:failures"
_OPEN_KEY = "cb:grpc_svc:open"


def _rpc_error(code: grpc.StatusCode) -> grpc.RpcError:
    return FakeRpcError(code)


@pytest.fixture()
def mock_cache():
    with patch("common.resilience.circuit_breaker.cache") as m:
        m.get.return_value = None
        m.add.return_value = True
        m.incr.return_value = 1
        yield m


class TestCircuitBreakerWithShouldTrip:
    def test_domain_error_does_not_increment_counter(self, mock_cache):
        """UNAUTHENTICATED (domain error) must NOT increment the failure counter."""
        domain_exc = _rpc_error(grpc.StatusCode.UNAUTHENTICATED)

        @circuit_breaker("grpc_svc", should_trip=is_grpc_infrastructure_error)
        def fn():
            raise domain_exc

        with pytest.raises(grpc.RpcError):
            fn()

        mock_cache.add.assert_not_called()
        mock_cache.incr.assert_not_called()

    def test_infrastructure_error_increments_counter(self, mock_cache):
        """UNAVAILABLE (infra error) MUST increment the failure counter."""
        infra_exc = _rpc_error(grpc.StatusCode.UNAVAILABLE)

        @circuit_breaker("grpc_svc", should_trip=is_grpc_infrastructure_error)
        def fn():
            raise infra_exc

        with pytest.raises(grpc.RpcError):
            fn()

        mock_cache.add.assert_called_once_with(_FAILURES_KEY, 0, timeout=60)
        mock_cache.incr.assert_called_once_with(_FAILURES_KEY)

    def test_already_exists_does_not_increment_counter(self, mock_cache):
        """ALREADY_EXISTS (domain) must NOT increment the failure counter."""
        domain_exc = _rpc_error(grpc.StatusCode.ALREADY_EXISTS)

        @circuit_breaker("grpc_svc", should_trip=is_grpc_infrastructure_error)
        def fn():
            raise domain_exc

        with pytest.raises(grpc.RpcError):
            fn()

        mock_cache.add.assert_not_called()

    def test_deadline_exceeded_increments_counter(self, mock_cache):
        """DEADLINE_EXCEEDED (infra) MUST increment the failure counter."""
        infra_exc = _rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED)

        @circuit_breaker("grpc_svc", should_trip=is_grpc_infrastructure_error)
        def fn():
            raise infra_exc

        with pytest.raises(grpc.RpcError):
            fn()

        mock_cache.incr.assert_called_once()

    def test_none_should_trip_preserves_original_behaviour(self, mock_cache):
        """Default None means all exceptions increment the counter (original behaviour)."""
        @circuit_breaker("grpc_svc")
        def fn():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            fn()

        mock_cache.incr.assert_called_once()

    def test_circuit_opens_after_threshold_infrastructure_errors(self, mock_cache):
        mock_cache.incr.return_value = 5  # at threshold

        infra_exc = _rpc_error(grpc.StatusCode.UNAVAILABLE)

        @circuit_breaker("grpc_svc", failure_threshold=5, should_trip=is_grpc_infrastructure_error)
        def fn():
            raise infra_exc

        with pytest.raises(grpc.RpcError):
            fn()

        mock_cache.set.assert_called_once_with(_OPEN_KEY, 1, timeout=30)

    def test_circuit_does_not_open_on_domain_errors(self, mock_cache):
        """Many UNAUTHENTICATED errors must never open the circuit."""
        mock_cache.incr.return_value = 100

        domain_exc = _rpc_error(grpc.StatusCode.UNAUTHENTICATED)

        @circuit_breaker("grpc_svc", failure_threshold=5, should_trip=is_grpc_infrastructure_error)
        def fn():
            raise domain_exc

        for _ in range(10):
            with pytest.raises(grpc.RpcError):
                fn()

        # open key must never be set
        set_calls = [c for c in mock_cache.set.call_args_list if c.args[0] == _OPEN_KEY]
        assert not set_calls
