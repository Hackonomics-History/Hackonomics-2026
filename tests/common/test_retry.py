"""Tests for the transient-error retry decorator."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from common.resilience.retry import retry_transient


class TestRetryTransient:
    def test_returns_on_first_success(self):
        @retry_transient(max_attempts=3)
        def fn():
            return "ok"

        assert fn() == "ok"

    def test_retries_on_timeout(self):
        call_count = 0

        @retry_transient(max_attempts=3, wait_seconds=0.0)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.Timeout("slow")
            return "recovered"

        result = fn()
        assert result == "recovered"
        assert call_count == 3

    def test_retries_on_connection_error(self):
        call_count = 0

        @retry_transient(max_attempts=2, wait_seconds=0.0)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.ConnectionError("refused")
            return "ok"

        assert fn() == "ok"
        assert call_count == 2

    def test_raises_after_max_attempts(self):
        @retry_transient(max_attempts=2, wait_seconds=0.0)
        def fn():
            raise requests.Timeout("always slow")

        with pytest.raises(requests.Timeout):
            fn()

    def test_does_not_retry_value_error(self):
        call_count = 0

        @retry_transient(max_attempts=3, wait_seconds=0.0)
        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("not transient")

        with pytest.raises(ValueError):
            fn()

        assert call_count == 1  # no retries

    def test_does_not_retry_generic_exception(self):
        call_count = 0

        @retry_transient(max_attempts=3, wait_seconds=0.0)
        def fn():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("unexpected")

        with pytest.raises(RuntimeError):
            fn()

        assert call_count == 1
