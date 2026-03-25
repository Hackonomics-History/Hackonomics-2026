import requests
from django.conf import settings


class CentralAuthAdapter:
    """HTTP adapter for the Go BFF Central-Auth service.

    The BFF is the single source of truth for identity.
    All authentication operations are delegated here.
    """

    def login(self, email: str, password: str, device_id: str, remember_me: bool) -> dict:
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/login",
            headers={"X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY},
            json={
                "email": email,
                "password": password,
                "device_id": device_id,
                "remember_me": remember_me,
            },
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )
        if res.status_code != 200:
            raise ValueError("Central-Auth login failed")
        return res.json()

    def signup(self, email: str, password: str) -> dict:
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/signup",
            headers={"X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY},
            json={"email": email, "password": password},
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )
        if res.status_code not in (200, 201):
            raise ValueError("Central-Auth signup failed")
        return res.json()

    def google_login(self, email: str, device_id: str) -> dict:
        """Issue BFF tokens for a Google-authenticated user identified by email."""
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/google/login",
            headers={"X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY},
            json={"email": email, "device_id": device_id},
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )
        if res.status_code != 200:
            raise ValueError("Central-Auth google login failed")
        return res.json()

    def refresh(self, refresh_token: str) -> dict:
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/refresh",
            headers={
                "X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY,
                "Authorization": f"Bearer {refresh_token}",
            },
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )
        if res.status_code != 200:
            raise ValueError("Refresh failed")
        return res.json()

    def logout(self, refresh_token: str):
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/logout",
            headers={
                "X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY,
                "Authorization": f"Bearer {refresh_token}",
            },
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )
        if res.status_code != 200:
            raise ValueError("Logout failed")
