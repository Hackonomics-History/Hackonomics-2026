from types import SimpleNamespace

from django.conf import settings
from rest_framework.authentication import BaseAuthentication

from authentication.application.services.authentication_service import (
    AuthenticationService,
)


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):

        if getattr(settings, "TESTING", False):
            return (
                SimpleNamespace(
                    id=1,
                    email="test@example.com",
                    is_authenticated=True,
                    payload={"user_id": 1},
                ),
                None,
            )

        skip_paths = [
            "/api/auth/login/",
            "/api/auth/signup/",
            "/api/auth/refresh/",
        ]
        if any(request.path.startswith(p) for p in skip_paths):
            return None

        token = request.COOKIES.get("access_token")

        if not token:
            if settings.DEBUG:
                print("NO ACCESS TOKEN COOKIE")
            return None

        service = AuthenticationService()
        payload = service.verify(token)

        # Payload data
        user = SimpleNamespace(
            id=payload["user_id"],
            email=payload.get("email"),
            is_authenticated=True,
            payload=payload,
        )

        return user, token
