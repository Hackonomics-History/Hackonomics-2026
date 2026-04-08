import base64
import hmac
import ipaddress
import logging
from dataclasses import dataclass
from typing import Optional

import jwt
import requests
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.authentication import BaseAuthentication

from common.resilience import circuit_breaker, retry_transient

logger = logging.getLogger(__name__)

_JWKS_CACHE_KEY = "ory_jwks_data"
_JWKS_STALE_CACHE_KEY = "ory_jwks_stale"  # indefinite copy served during outages
_JWKS_DEFAULT_TTL = 300  # 5 minutes
# Lock key used to rate-limit JWKS force-refresh (prevents DoS amplification)
_JWKS_REFRESH_LOCK_KEY = "ory_jwks_refresh_lock"
_JWKS_REFRESH_LOCK_TTL = 30  # seconds — only one refresh per 30-second window


@circuit_breaker("jwks_fetch", failure_threshold=3, recovery_timeout=20)
@retry_transient(max_attempts=2, wait_seconds=0.1)
def _jwks_http_get(url: str, timeout: int) -> requests.Response:
    """HTTP GET for JWKS with circuit breaker (outer) and retry (inner).

    Circuit opens after 3 failures in 60s; stays open for 20s.
    When open, callers fall through to the stale-cache path immediately
    without queuing a 5-second timeout wait.
    """
    return requests.get(url, timeout=timeout)


@dataclass
class OryIdentityProxy:
    """Lightweight identity object injected into request.user by JWKSMiddleware.

    Replaces Django's auth_user-backed User with the Ory identity from the JWT.
    The Go BFF is the single source of truth for identity; Django is read-only.
    """

    ory_id: str
    email: str
    is_authenticated: bool = True
    is_anonymous: bool = False
    is_staff: bool = False
    is_superuser: bool = False

    @property
    def pk(self) -> str:
        return self.ory_id

    @property
    def id(self) -> str:
        # Backward-compat alias so existing .id accesses still resolve
        return self.ory_id

    def __str__(self) -> str:
        return self.ory_id


class MiddlewarePassthroughAuthentication(BaseAuthentication):
    """DRF authentication shim that reads request.user set by JWKSMiddleware.

    DRF builds its own Request wrapper and ignores Django middleware unless an
    authentication class explicitly hands the user object back. This class
    bridges the two layers: if the middleware already validated the JWT and set
    an OryIdentityProxy on the underlying WSGI request, we return it directly.
    """

    def authenticate(self, request):
        wsgi_user = getattr(request._request, "user", None)
        if wsgi_user is not None and getattr(wsgi_user, "is_authenticated", False):
            return (wsgi_user, None)
        return None

    def authenticate_header(self, request) -> str:
        return "Bearer"


class JWKSMiddleware:
    """Django middleware that validates JWTs locally using the Go BFF JWKS endpoint.

    Token transport priority:
      1. Authorization: Bearer <token> header
      2. access_token httpOnly cookie (transition fallback)

    Injects OryIdentityProxy into request.user on success.
    On any failure (expired, malformed, JWKS unavailable) sets AnonymousUser
    without leaking internal error details to the response.
    """

    _SKIP_PREFIXES = (
        "/api/auth/login/",
        "/api/auth/signup/",
        "/api/auth/refresh/",
        "/api/auth/google/",
        "/admin/",
        "/-/",  # health probes
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # In test mode inject a stable test identity so the full middleware chain
        # runs without a real JWKS endpoint. Guarded to never activate in production.
        if getattr(settings, "TESTING", False):
            assert not getattr(settings, "IS_PRODUCTION", False), (
                "TESTING=True must never be set in a production environment"
            )
            request.user = OryIdentityProxy(
                ory_id="00000000-0000-0000-0000-000000000001",
                email="test@example.com",
            )
            return self.get_response(request)

        # HIGH-3: /metrics requires Basic Auth when credentials are configured.
        if request.path == "/metrics":
            return self._handle_metrics_auth(request)

        # Paths that are public or handled by a different auth mechanism
        if any(request.path.startswith(prefix) for prefix in self._SKIP_PREFIXES):
            return self.get_response(request)

        token = self._extract_token(request)

        if not token:
            request.user = AnonymousUser()
            return self.get_response(request)

        try:
            payload = self._decode_token(token)
            request.user = OryIdentityProxy(
                ory_id=payload["sub"],
                email=payload.get("email", ""),
            )
        except jwt.ExpiredSignatureError:
            logger.warning("JWT validation failed: token expired")
            request.user = AnonymousUser()
        except jwt.InvalidTokenError as exc:
            # Log only the exception type — never the raw token value
            logger.warning("JWT validation failed: %s", type(exc).__name__)
            request.user = AnonymousUser()
        except Exception as exc:
            logger.warning("JWT validation error: %s", type(exc).__name__)
            request.user = AnonymousUser()

        return self.get_response(request)

    # ── private helpers ──────────────────────────────────────────────────────

    def _handle_metrics_auth(self, request):
        """Gate /metrics behind a double-lock: IP CIDR allowlist AND Basic Auth.

        Lock 1 — IP CIDR (METRICS_ALLOWED_CIDR, comma-separated):
          Empty in dev → open access (no IP check).
          IP not in any listed CIDR → 403, no WWW-Authenticate (don't leak auth info).

        Lock 2 — Basic Auth (METRICS_BASIC_AUTH_USER/PASSWORD):
          Both empty in dev → check skipped, CIDR-only mode.
          Missing/wrong Authorization header → 401 + WWW-Authenticate challenge.

        Both locks must pass independently. IP is checked first so that
        out-of-range scrapers cannot probe for valid credentials.
        """
        # ── Lock 1: IP CIDR ───────────────────────────────────────────────────
        allowed_cidr_raw = getattr(settings, "METRICS_ALLOWED_CIDR", "")
        if allowed_cidr_raw:
            remote_addr = request.META.get("REMOTE_ADDR", "")
            try:
                client_ip = ipaddress.ip_address(remote_addr)
            except ValueError:
                return HttpResponse(status=403)
            in_allowlist = any(
                client_ip in ipaddress.ip_network(cidr.strip(), strict=False)
                for cidr in allowed_cidr_raw.split(",")
                if cidr.strip()
            )
            if not in_allowlist:
                return HttpResponse(status=403)

        # ── Lock 2: Basic Auth ────────────────────────────────────────────────
        expected_user = getattr(settings, "METRICS_BASIC_AUTH_USER", "")
        expected_pass = getattr(settings, "METRICS_BASIC_AUTH_PASSWORD", "")
        if not expected_user or not expected_pass:
            return self.get_response(request)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                provided_user, provided_pass = decoded.split(":", 1)
                if (
                    hmac.compare_digest(provided_user, expected_user)
                    and hmac.compare_digest(provided_pass, expected_pass)
                ):
                    return self.get_response(request)
            except Exception:
                pass

        response = HttpResponse(status=401)
        response["WWW-Authenticate"] = 'Basic realm="metrics"'
        return response

    def _extract_token(self, request) -> Optional[str]:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        # Cookie fallback for clients not yet sending Authorization header
        return request.COOKIES.get("access_token") or None

    def _decode_token(self, token: str) -> dict:
        """Decode and verify the JWT using cached JWKS public keys.

        On InvalidSignatureError (possible key rotation), performs at most one
        JWKS refresh per 30-second window across all workers to prevent DoS
        amplification via crafted tokens (HIGH-2 fix).
        """
        try:
            return self._verify_with_jwks(token, force_refresh=False)
        except jwt.InvalidSignatureError:
            # Rate-limit the forced refresh using a distributed lock in Redis.
            # cache.add() is atomic: returns True only if the key did not exist.
            acquired = cache.add(_JWKS_REFRESH_LOCK_KEY, 1, _JWKS_REFRESH_LOCK_TTL)
            if not acquired:
                # Another worker already refreshed recently; fail without re-fetching
                raise
            logger.info("JWT signature invalid; forcing JWKS refresh for key rotation")
            cache.delete(_JWKS_CACHE_KEY)
            return self._verify_with_jwks(token, force_refresh=True)

    def _verify_with_jwks(self, token: str, force_refresh: bool) -> dict:
        jwks_data = self._get_jwks(force_refresh=force_refresh)

        # Resolve the signing key by kid (key ID) from the JWT header
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        signing_key = self._select_key(jwks_data, kid)

        decode_kwargs: dict = {
            "algorithms": ["RS256", "ES256"],
            "options": {"verify_exp": True, "verify_nbf": True},
        }
        # Verify issuer if configured. Set EXPECTED_JWT_ISSUER in env to match
        # the Go BFF's iss claim (e.g. "https://bff.example.com"). Required in
        # production; logs a warning in non-production if absent (CRITICAL-2).
        expected_issuer = getattr(settings, "EXPECTED_JWT_ISSUER", None)
        if expected_issuer:
            decode_kwargs["issuer"] = expected_issuer
        elif getattr(settings, "IS_PRODUCTION", False):
            raise jwt.InvalidTokenError("EXPECTED_JWT_ISSUER is not configured")
        else:
            logger.warning("EXPECTED_JWT_ISSUER not set; skipping iss verification (dev only)")

        # HIGH-1: Verify aud claim when EXPECTED_JWT_AUDIENCE is configured.
        expected_audience = getattr(settings, "EXPECTED_JWT_AUDIENCE", None)
        if expected_audience:
            decode_kwargs["audience"] = expected_audience

        return jwt.decode(token, signing_key.key, **decode_kwargs)

    def _select_key(self, jwks_data: dict, kid: Optional[str]):
        """Return the PyJWK matching the given key ID, or the first key if no kid."""
        jwks = jwt.PyJWKSet.from_dict(jwks_data)
        for key in jwks.keys:
            if kid is None or key.key_id == kid:
                return key
        raise jwt.InvalidKeyError("No matching signing key found in JWKS")

    def _get_jwks(self, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = cache.get(_JWKS_CACHE_KEY)
            if cached is not None:
                return cached
        return self._fetch_and_cache_jwks()

    def _fetch_and_cache_jwks(self) -> dict:
        jwks_url = getattr(
            settings,
            "JWKS_URL",
            f"{settings.CENTRAL_AUTH_URL}/.well-known/jwks.json",
        )
        ttl = getattr(settings, "JWKS_CACHE_TTL", _JWKS_DEFAULT_TTL)
        timeout = getattr(settings, "CENTRAL_AUTH_TIMEOUT", 5)

        try:
            resp = _jwks_http_get(jwks_url, timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            # Never surface the URL or raw error to callers.
            logger.error("JWKS fetch error: %s", type(exc).__name__)
            # Fall back to stale keys rather than rejecting every request during
            # a brief Kratos outage. Keys rotate infrequently; stale is safe.
            stale = cache.get(_JWKS_STALE_CACHE_KEY)
            if stale is not None:
                logger.warning(
                    "Serving stale JWKS after fetch failure (%s)", type(exc).__name__
                )
                return stale
            raise jwt.InvalidTokenError("Token cannot be validated: JWKS unavailable") from None

        cache.set(_JWKS_CACHE_KEY, data, timeout=ttl)
        # Store an indefinite stale copy — served only when live fetch fails.
        cache.set(_JWKS_STALE_CACHE_KEY, data, timeout=None)
        return data
