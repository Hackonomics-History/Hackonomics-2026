"""Integration tests for the gRPC circuit breaker + retry composition.

These tests exercise the full decorator stack as composed in grpc_auth_service.py:
  circuit_breaker(should_trip=is_grpc_infrastructure_error)
  └── retry_transient_grpc(max_attempts=2)
      └── underlying gRPC call
"""
from unittest.mock import MagicMock, call, patch

import grpc
import pytest

from common.resilience.circuit_breaker import CircuitOpenError, circuit_breaker
from common.resilience.grpc_errors import is_grpc_infrastructure_error
from common.resilience.retry import retry_transient_grpc
from tests.conftest import FakeRpcError


def _rpc_error(code: grpc.StatusCode) -> grpc.RpcError:
    return FakeRpcError(code)


@pytest.fixture()
def mock_cache():
    with patch("common.resilience.circuit_breaker.cache") as m:
        m.get.return_value = None
        m.add.return_value = True
        m.incr.return_value = 1
        yield m


class TestRetryTransientGrpc:
    def test_retries_on_unavailable_then_succeeds(self):
        """Two UNAVAILABLE errors then success → retry works, returns result."""
        call_count = {"n": 0}

        @retry_transient_grpc(max_attempts=3, wait_seconds=0)
        def rpc():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise _rpc_error(grpc.StatusCode.UNAVAILABLE)
            return "ok"

        assert rpc() == "ok"
        assert call_count["n"] == 3

    def test_does_not_retry_on_unauthenticated(self):
        """UNAUTHENTICATED (domain error) must NOT be retried."""
        call_count = {"n": 0}

        @retry_transient_grpc(max_attempts=3, wait_seconds=0)
        def rpc():
            call_count["n"] += 1
            raise _rpc_error(grpc.StatusCode.UNAUTHENTICATED)

        with pytest.raises(grpc.RpcError):
            rpc()

        assert call_count["n"] == 1  # no retry

    def test_exhausts_retries_on_persistent_unavailable(self):
        """UNAVAILABLE persisting across all attempts → re-raises after max_attempts."""
        call_count = {"n": 0}

        @retry_transient_grpc(max_attempts=2, wait_seconds=0)
        def rpc():
            call_count["n"] += 1
            raise _rpc_error(grpc.StatusCode.UNAVAILABLE)

        with pytest.raises(grpc.RpcError):
            rpc()

        assert call_count["n"] == 2


class TestCircuitBreakerGrpcComposition:
    def test_circuit_opens_after_threshold_unavailable(self, mock_cache):
        """5 consecutive UNAVAILABLE errors trip the circuit."""
        mock_cache.incr.return_value = 5  # at threshold

        @circuit_breaker("integ_svc", failure_threshold=5, should_trip=is_grpc_infrastructure_error)
        def rpc():
            raise _rpc_error(grpc.StatusCode.UNAVAILABLE)

        with pytest.raises(grpc.RpcError):
            rpc()

        mock_cache.set.assert_called_with("cb:integ_svc:open", 1, timeout=30)

    def test_circuit_never_opens_on_unauthenticated(self, mock_cache):
        """Repeated UNAUTHENTICATED errors must never open the circuit."""
        mock_cache.incr.return_value = 100  # simulate high count if it were counted

        @circuit_breaker("integ_svc", failure_threshold=5, should_trip=is_grpc_infrastructure_error)
        def rpc():
            raise _rpc_error(grpc.StatusCode.UNAUTHENTICATED)

        for _ in range(10):
            with pytest.raises(grpc.RpcError):
                rpc()

        # open key must never be set — incr was never called
        set_calls = [c for c in mock_cache.set.call_args_list if "open" in str(c)]
        assert not set_calls
        mock_cache.incr.assert_not_called()

    def test_circuit_never_opens_on_already_exists(self, mock_cache):
        mock_cache.incr.return_value = 100

        @circuit_breaker("integ_svc", failure_threshold=5, should_trip=is_grpc_infrastructure_error)
        def rpc():
            raise _rpc_error(grpc.StatusCode.ALREADY_EXISTS)

        for _ in range(10):
            with pytest.raises(grpc.RpcError):
                rpc()

        mock_cache.incr.assert_not_called()
