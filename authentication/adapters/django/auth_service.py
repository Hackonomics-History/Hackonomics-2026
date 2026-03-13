import requests
from django.conf import settings


class CentralAuthAdapter:
    def login(self, user_id: str, device_id: str, remember_me: bool) -> dict:
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/login",
            headers={
                "X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY,
            },
            json={
                "user_id": user_id,
                "device_id": device_id,
                "remember_me": remember_me,
            },
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )
        if res.status_code != 200:
            raise ValueError("Central-Auth login failed")
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

    def verify(self, access_token: str):
        res = requests.post(
            f"{settings.CENTRAL_AUTH_URL}/auth/verify",
            headers={
                "X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=settings.CENTRAL_AUTH_TIMEOUT,
        )

        if res.status_code != 200:
            raise Exception("Invalid token")

        return res.json()
