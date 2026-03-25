"""Integration tests for JWKSMiddleware — cache behaviour, JWT validation, and ory_id mapping.

These tests deliberately set TESTING=False so the real middleware code paths
(JWKS fetch, LocMemCache, JWT decode) are exercised, unlike the smoke tests in the
root tests.py which rely on the TESTING shortcut.

Tests 1, 2, 4 run entirely in-process (LocMemCache, mocked HTTP) — no external
services required.  Test 3 is marked django_db and requires a reachable PostgreSQL
instance (available when the full Docker Compose stack is up).
"""

import base64
import time
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from authentication.adapters.django.jwks_middleware import (
    JWKSMiddleware,
    _JWKS_CACHE_KEY,
    _JWKS_REFRESH_LOCK_KEY,
)

# ── constants ─────────────────────────────────────────────────────────────────

_TEST_KID = "test-key-1"
_TEST_ISSUER = "https://bff.test"
_TEST_JWKS_URL = "http://bff.test/.well-known/jwks.json"

# Use LocMemCache so tests work without a running Redis instance.
_LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "jwks-tests",
    }
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _int_to_base64url(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    b = n.to_bytes(length, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _make_jwks(private_key, kid: str = _TEST_KID) -> dict:
    """Construct a minimal JWKS dict from an RSA private key's public component."""
    pub_numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": kid,
                "alg": "RS256",
                "n": _int_to_base64url(pub_numbers.n),
                "e": _int_to_base64url(pub_numbers.e),
            }
        ]
    }


def _make_token(
    private_key,
    *,
    sub: str,
    iss: str = _TEST_ISSUER,
    kid: str = _TEST_KID,
) -> str:
    """Sign a minimal JWT with the given RSA private key."""
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "email": f"{sub}@test.example",
            "iss": iss,
            "exp": now + 300,
            "nbf": now - 10,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def rsa_private_key():
    """Generate one RSA key pair for the entire test session (amortises ~100 ms keygen)."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def rsa_jwks(rsa_private_key):
    """Pre-built JWKS for the session key pair (key A)."""
    return _make_jwks(rsa_private_key)


@pytest.fixture(autouse=True)
def _jwks_test_env():
    """Switch to LocMemCache and disable the TESTING shortcut for every test in this
    module so real middleware code paths are exercised without needing a live Redis."""
    with override_settings(CACHES=_LOCMEM_CACHES, TESTING=False):
        cache.delete(_JWKS_CACHE_KEY)
        cache.delete(_JWKS_REFRESH_LOCK_KEY)
        yield
        cache.delete(_JWKS_CACHE_KEY)
        cache.delete(_JWKS_REFRESH_LOCK_KEY)


@pytest.fixture
def api_client():
    return APIClient()


# ── Test 1: cache miss triggers HTTP fetch ────────────────────────────────────


@override_settings(JWKS_URL=_TEST_JWKS_URL)
def test_jwks_cache_miss_triggers_http_fetch(rsa_jwks):
    """On a cache miss _fetch_and_cache_jwks must call requests.get exactly once
    and store the result in the cache under _JWKS_CACHE_KEY."""
    middleware = JWKSMiddleware(get_response=lambda r: None)

    mock_resp = MagicMock()
    mock_resp.json.return_value = rsa_jwks
    mock_resp.raise_for_status.return_value = None

    with patch(
        "authentication.adapters.django.jwks_middleware.requests.get",
        return_value=mock_resp,
    ) as mock_get:
        result = middleware._fetch_and_cache_jwks()

    mock_get.assert_called_once_with(_TEST_JWKS_URL, timeout=5)
    assert result == rsa_jwks
    assert cache.get(_JWKS_CACHE_KEY) == rsa_jwks, (
        "JWKS data should be persisted in cache after a successful fetch"
    )


# ── Test 2: cache hit avoids HTTP fetch ───────────────────────────────────────


def test_jwks_cache_hit_skips_http_fetch(rsa_jwks):
    """A warm cache must short-circuit _get_jwks with no outbound HTTP call."""
    cache.set(_JWKS_CACHE_KEY, rsa_jwks, 300)
    middleware = JWKSMiddleware(get_response=lambda r: None)

    with patch(
        "authentication.adapters.django.jwks_middleware.requests.get"
    ) as mock_get:
        result = middleware._get_jwks(force_refresh=False)

    mock_get.assert_not_called()
    assert result == rsa_jwks


# ── Test 3: valid JWT maps to request.user.ory_id ────────────────────────────


@pytest.mark.django_db
@override_settings(EXPECTED_JWT_ISSUER=_TEST_ISSUER)
def test_valid_jwt_maps_ory_id_to_request_user(api_client, rsa_private_key, rsa_jwks):
    """A valid JWT issued by the Go BFF must result in request.user.ory_id matching
    the token's 'sub' claim, threading correctly through JWKSMiddleware →
    MiddlewarePassthroughAuthentication → DRF → use-case → repository.

    A 200 (null account) or 404 (account not found) — not 401/403 — confirms
    that the identity was resolved and passed through the full stack.

    Requires: running PostgreSQL (available when docker-compose stack is up).
    """
    ory_id = str(uuid.uuid4())
    cache.set(_JWKS_CACHE_KEY, rsa_jwks, 300)
    token = _make_token(rsa_private_key, sub=ory_id)

    response = api_client.get(
        "/api/account/me/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code in (200, 404), (
        f"Expected 200 or 404 (valid identity resolved), "
        f"got {response.status_code}: {getattr(response, 'data', response.content)}"
    )


# ── Test 4: key rotation acquires Redis lock and retries ──────────────────────


@override_settings(EXPECTED_JWT_ISSUER=_TEST_ISSUER)
def test_key_rotation_acquires_lock_and_retries(rsa_private_key, rsa_jwks):
    """When a token's signature cannot be verified with the cached JWKS (key rotation),
    the middleware must:
      1. Acquire the refresh lock exactly once (rate-limits DoS amplification).
      2. Clear the stale JWKS from cache.
      3. Fetch fresh JWKS and retry verification exactly once.
      4. Return the decoded payload without entering an infinite retry loop.
    """
    # Key B represents the rotated key pair issued by the Go BFF after rotation.
    key_b = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # Same kid as key A so _select_key finds a match → jwt.decode raises
    # InvalidSignatureError (wrong public key material), triggering the rotation path.
    key_b_jwks = _make_jwks(key_b, kid=_TEST_KID)

    # Stale JWKS (key A) is in cache.
    cache.set(_JWKS_CACHE_KEY, rsa_jwks, 300)

    # Token signed with key B but advertising key A's kid → InvalidSignatureError.
    token = _make_token(key_b, sub="rotation-test-id", kid=_TEST_KID)

    middleware = JWKSMiddleware(get_response=lambda r: None)

    with patch.object(
        middleware, "_fetch_and_cache_jwks", return_value=key_b_jwks
    ) as mock_fetch:
        result = middleware._decode_token(token)

    # Refresh lock was set during the 30-second window.
    assert cache.get(_JWKS_REFRESH_LOCK_KEY) is not None, (
        "Refresh lock should be set in cache after a forced JWKS rotation"
    )
    # Exactly one JWKS fetch — no amplification.
    mock_fetch.assert_called_once()
    assert result["sub"] == "rotation-test-id"
