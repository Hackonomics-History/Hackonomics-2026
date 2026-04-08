"""Tests for the Redis-backed circuit breaker."""
from unittest.mock import MagicMock, call, patch

import pytest

from common.resilience.circuit_breaker import CircuitOpenError, circuit_breaker

_OPEN_KEY = "cb:svc:open"
_FAILURES_KEY = "cb:svc:failures"


def _make_breaker(threshold=3, recovery=30, window=60):
    return circuit_breaker("svc", failure_threshold=threshold, recovery_timeout=recovery, failure_window=window)


@pytest.fixture()
def mock_cache():
    with patch("common.resilience.circuit_breaker.cache") as m:
        m.get.return_value = None   # circuit CLOSED by default
        m.add.return_value = True
        m.incr.return_value = 1
        yield m


class TestCircuitBreakerClosed:
    def test_passes_through_on_success(self, mock_cache):
        @_make_breaker()
        def fn():
            return "ok"

        assert fn() == "ok"

    def test_deletes_failure_counter_on_success(self, mock_cache):
        @_make_breaker()
        def fn():
            return "ok"

        fn()
        mock_cache.delete.assert_called_once_with(_FAILURES_KEY)

    def test_propagates_exception(self, mock_cache):
        @_make_breaker()
        def fn():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fn()

    def test_increments_failure_counter(self, mock_cache):
        mock_cache.incr.return_value = 1  # below threshold

        @_make_breaker(threshold=3)
        def fn():
            raise ValueError()

        with pytest.raises(ValueError):
            fn()

        mock_cache.add.assert_called_once_with(_FAILURES_KEY, 0, timeout=60)
        mock_cache.incr.assert_called_once_with(_FAILURES_KEY)


class TestCircuitBreakerOpens:
    def test_opens_after_reaching_threshold(self, mock_cache):
        mock_cache.incr.return_value = 3  # exactly at threshold

        @_make_breaker(threshold=3, recovery=30)
        def fn():
            raise ValueError()

        with pytest.raises(ValueError):
            fn()

        mock_cache.set.assert_called_once_with(_OPEN_KEY, 1, timeout=30)
        mock_cache.delete.assert_called_with(_FAILURES_KEY)

    def test_does_not_open_below_threshold(self, mock_cache):
        mock_cache.incr.return_value = 2  # below threshold=3

        @_make_breaker(threshold=3)
        def fn():
            raise ValueError()

        with pytest.raises(ValueError):
            fn()

        # open key must not be set
        set_calls = [c for c in mock_cache.set.call_args_list if c.args[0] == _OPEN_KEY]
        assert not set_calls


class TestCircuitBreakerOpen:
    def test_fails_fast_when_open(self, mock_cache):
        mock_cache.get.return_value = 1  # circuit is OPEN

        @_make_breaker()
        def fn():
            return "should not reach"

        with pytest.raises(CircuitOpenError) as exc_info:
            fn()

        assert exc_info.value.service_name == "svc"

    def test_does_not_call_underlying_function_when_open(self, mock_cache):
        mock_cache.get.return_value = 1
        called = []

        @_make_breaker()
        def fn():
            called.append(True)
            return "ok"

        with pytest.raises(CircuitOpenError):
            fn()

        assert not called


class TestCircuitBreakerHalfOpen:
    def test_circuit_open_not_re_counted_as_failure(self, mock_cache):
        """CircuitOpenError from a nested call must not increment the failure counter."""
        mock_cache.get.return_value = None  # outer circuit CLOSED

        @_make_breaker()
        def inner():
            raise CircuitOpenError("other_svc")

        with pytest.raises(CircuitOpenError):
            inner()

        # incr must not have been called for a CircuitOpenError
        mock_cache.incr.assert_not_called()
