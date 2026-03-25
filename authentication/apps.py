import logging
import sys

import requests
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"

    def ready(self):
        import authentication.adapters.django.jwt_authentication_schema  # noqa: F401
        self._check_central_auth_service_key()

    def _check_central_auth_service_key(self):
        """Verify CENTRAL_AUTH_SERVICE_KEY is accepted by Central-auth at startup.

        Only runs in production (IS_PRODUCTION=True). Treats Central-auth being
        unreachable as a warning (not fatal) so that management commands like
        migrate can run without Central-auth being up. A 401 response, however,
        means the service key is actively rejected — that is always fatal.
        """
        from django.conf import settings

        if not getattr(settings, "IS_PRODUCTION", False):
            return

        url = f"{settings.CENTRAL_AUTH_URL}/auth/verify"
        try:
            resp = requests.post(
                url,
                headers={"X-Service-Key": settings.CENTRAL_AUTH_SERVICE_KEY},
                json={},
                timeout=settings.CENTRAL_AUTH_TIMEOUT,
            )
            if resp.status_code == 401:
                # Distinguish middleware rejection ("invalid service key") from
                # handler rejection ("missing token" — key was accepted, just no
                # JWT provided, which is expected for this probe).
                try:
                    body_error = resp.json().get("error", "")
                except Exception:
                    body_error = ""
                if "invalid service key" in body_error or "missing service key" in body_error:
                    print(
                        "[FATAL] CENTRAL_AUTH_SERVICE_KEY mismatch — "
                        "service key rejected by Central-auth",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                # "missing token" 401 means the key was accepted — service reachable and key valid.
            logger.info(
                "[startup] Central-auth service key verified (HTTP %d)", resp.status_code
            )
        except requests.exceptions.ConnectionError:
            logger.warning(
                "[startup] Central-auth unreachable at %s — skipping service key check",
                url,
            )
        except requests.exceptions.Timeout:
            logger.warning(
                "[startup] Central-auth timed out after %ss — skipping service key check",
                settings.CENTRAL_AUTH_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "[startup] Central-auth check failed (%s) — skipping service key check",
                type(exc).__name__,
            )
