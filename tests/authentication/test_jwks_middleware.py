"""Tests for JWKSMiddleware resilience additions — stale cache and circuit breaker."""
from unittest.mock import MagicMock, patch

import jwt
import pytest

from authentication.adapters.django.jwks_middleware import (
    JWKSMiddleware,
    _JWKS_STALE_CACHE_KEY,
    _JWKS_CACHE_KEY,
)
from common.resilience.circuit_breaker import CircuitOpenError

_MIDDLEWARE_MODULE = "authentication.adapters.django.jwks_middleware"

_MOCK_JWKS = {"keys": [{"kty": "RSA", "kid": "key1", "n": "abc", "e": "AQAB"}]}


def _make_middleware():
    return JWKSMiddleware(get_response=MagicMock())


class TestFetchAndCacheJwks:
    """Unit tests for _fetch_and_cache_jwks — covers stale fallback and circuit breaker."""

    def test_caches_fresh_jwks_on_success(self, settings):
        settings.JWKS_URL = "http://auth/.well-known/jwks.json"
        settings.JWKS_CACHE_TTL = 300
        settings.CENTRAL_AUTH_TIMEOUT = 5

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = _MOCK_JWKS

        with patch(f"{_MIDDLEWARE_MODULE}._jwks_http_get", return_value=resp) as mock_get, \
             patch(f"{_MIDDLEWARE_MODULE}.cache") as mock_cache:
            mock_cache.get.return_value = None  # no stale data
            middleware = _make_middleware()
            result = middleware._fetch_and_cache_jwks()

        assert result == _MOCK_JWKS
        # Both live TTL and indefinite stale copies must be stored
        calls = {c.args[0]: c for c in mock_cache.set.call_args_list}
        assert _JWKS_CACHE_KEY in calls
        assert _JWKS_STALE_CACHE_KEY in calls
        assert calls[_JWKS_STALE_CACHE_KEY].args[2] is None  # timeout=None → indefinite

    def test_serves_stale_cache_when_fetch_raises(self, settings):
        settings.JWKS_URL = "http://auth/.well-known/jwks.json"
        settings.JWKS_CACHE_TTL = 300
        settings.CENTRAL_AUTH_TIMEOUT = 5

        with patch(f"{_MIDDLEWARE_MODULE}._jwks_http_get", side_effect=Exception("timeout")), \
             patch(f"{_MIDDLEWARE_MODULE}.cache") as mock_cache:
            mock_cache.get.return_value = _MOCK_JWKS  # stale data present

            middleware = _make_middleware()
            result = middleware._fetch_and_cache_jwks()

        assert result == _MOCK_JWKS

    def test_serves_stale_cache_when_circuit_open(self, settings):
        settings.JWKS_URL = "http://auth/.well-known/jwks.json"
        settings.JWKS_CACHE_TTL = 300
        settings.CENTRAL_AUTH_TIMEOUT = 5

        with patch(f"{_MIDDLEWARE_MODULE}._jwks_http_get", side_effect=CircuitOpenError("jwks_fetch")), \
             patch(f"{_MIDDLEWARE_MODULE}.cache") as mock_cache:
            mock_cache.get.return_value = _MOCK_JWKS  # stale present

            middleware = _make_middleware()
            result = middleware._fetch_and_cache_jwks()

        assert result == _MOCK_JWKS

    def test_raises_invalid_token_error_when_no_stale_cache(self, settings):
        settings.JWKS_URL = "http://auth/.well-known/jwks.json"
        settings.JWKS_CACHE_TTL = 300
        settings.CENTRAL_AUTH_TIMEOUT = 5

        with patch(f"{_MIDDLEWARE_MODULE}._jwks_http_get", side_effect=Exception("network error")), \
             patch(f"{_MIDDLEWARE_MODULE}.cache") as mock_cache:
            mock_cache.get.return_value = None  # no stale data

            middleware = _make_middleware()
            with pytest.raises(jwt.InvalidTokenError, match="JWKS unavailable"):
                middleware._fetch_and_cache_jwks()

    def test_raises_on_bad_status_code(self, settings):
        settings.JWKS_URL = "http://auth/.well-known/jwks.json"
        settings.JWKS_CACHE_TTL = 300
        settings.CENTRAL_AUTH_TIMEOUT = 5

        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("404 Not Found")

        with patch(f"{_MIDDLEWARE_MODULE}._jwks_http_get", return_value=resp), \
             patch(f"{_MIDDLEWARE_MODULE}.cache") as mock_cache:
            mock_cache.get.return_value = None

            middleware = _make_middleware()
            with pytest.raises(jwt.InvalidTokenError):
                middleware._fetch_and_cache_jwks()
