import logging

import requests
from django.conf import settings

from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from common.resilience import CircuitOpenError, circuit_breaker, retry_transient

logger = logging.getLogger(__name__)


@circuit_breaker("central_auth", failure_threshold=5, recovery_timeout=30)
@retry_transient(max_attempts=2, wait_seconds=0.3)
def _central_auth_http(
    method: str,
    url: str,
    *,
    headers: dict,
    json: dict | None = None,
    timeout: int,
) -> requests.Response:
    """Low-level HTTP call to Central-auth.

    Decorated with circuit breaker (outer) and retry (inner):
    - Circuit OPEN  → raises CircuitOpenError immediately (no network call).
    - Transient err → retried once with 300 ms exponential backoff.
    - Persistent err → raises after max_attempts; circuit records a failure.
    """
    return requests.request(method, url, headers=headers, json=json, timeout=timeout)


def _service_headers(extra: dict | None = None) -> dict:
    headers = {"X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY}
    if extra:
        headers.update(extra)
    return headers


class CentralAuthAdapter:
    """HTTP adapter for the Go BFF Central-Auth service.

    The BFF is the single source of truth for identity.
    All authentication operations are delegated here.

    Every public method translates low-level network/circuit failures into typed
    ``BusinessException`` so callers never need to handle ``requests`` exceptions.
    """

    def _call(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict | None = None,
    ) -> requests.Response:
        url = f"{settings.CENTRAL_AUTH_URL}{path}"
        try:
            return _central_auth_http(
                method,
                url,
                headers=_service_headers(extra_headers),
                json=json,
                timeout=settings.CENTRAL_AUTH_TIMEOUT,
            )
        except CircuitOpenError:
            logger.warning(
                "Central-auth circuit open — failing fast [%s %s]", method, path
            )
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
        except requests.Timeout:
            logger.error("Central-auth timeout [%s %s]", method, path)
            raise BusinessException(ErrorCode.TIMEOUT)
        except requests.ConnectionError:
            logger.error("Central-auth connection error [%s %s]", method, path)
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)

    def login(self, email: str, password: str, device_id: str, remember_me: bool) -> dict:
        res = self._call(
            "POST",
            "/auth/login",
            json={
                "email": email,
                "password": password,
                "device_id": device_id,
                "remember_me": remember_me,
            },
        )
        if res.status_code != 200:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
        return res.json()

    def signup(self, email: str, password: str) -> dict:
        res = self._call(
            "POST",
            "/auth/signup",
            json={"email": email, "password": password},
        )
        if res.status_code not in (200, 201):
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
        return res.json()

    def google_login(self, email: str, device_id: str) -> dict:
        """Issue BFF tokens for a Google-authenticated user identified by email."""
        res = self._call(
            "POST",
            "/auth/google/login",
            json={"email": email, "device_id": device_id},
        )
        if res.status_code != 200:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
        return res.json()

    def refresh(self, refresh_token: str) -> dict:
        res = self._call(
            "POST",
            "/auth/refresh",
            extra_headers={"Authorization": f"Bearer {refresh_token}"},
        )
        if res.status_code != 200:
            raise BusinessException(ErrorCode.REFRESH_TOKEN_INVALID)
        return res.json()

    def logout(self, refresh_token: str) -> None:
        res = self._call(
            "POST",
            "/auth/logout",
            extra_headers={"Authorization": f"Bearer {refresh_token}"},
        )
        if res.status_code != 200:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
