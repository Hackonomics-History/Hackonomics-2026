"""Celery tasks for the authentication domain."""
import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from authentication.adapters.django.jwks_middleware import (
    _JWKS_CACHE_KEY,
    _JWKS_DEFAULT_TTL,
    _JWKS_STALE_CACHE_KEY,
    _JWKS_STALE_TTL,
    _jwks_http_get,
)

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=60,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def refresh_jwks_cache(self) -> None:
    """Proactively refresh the JWKS cache from Central-auth every hour.

    Runs as a Celery-beat periodic task so that the 'fresh' cache key is
    always warm before it expires. This prevents the first request after
    cache expiry from bearing the latency of a synchronous JWKS fetch.

    Resilience:
    - The stale copy (_JWKS_STALE_CACHE_KEY) is updated on every successful
      refresh, extending the 30-minute stale window.
    - On failure the task retries up to 3 times with exponential backoff
      (60s → 120s → 240s). If all retries fail the stale cache continues to
      serve authentication until the next scheduled run.
    - The circuit breaker wrapping _jwks_http_get prevents retry storms
      against a down Central-auth endpoint.
    """
    task_id = getattr(self.request, "id", None)
    jwks_url = getattr(
        settings,
        "JWKS_URL",
        f"{settings.CENTRAL_AUTH_URL}/.well-known/jwks.json",
    )
    ttl = getattr(settings, "JWKS_CACHE_TTL", _JWKS_DEFAULT_TTL)
    timeout = getattr(settings, "CENTRAL_AUTH_TIMEOUT", 5)

    logger.info("[jwks-refresh:%s] starting scheduled JWKS cache refresh", task_id)
    try:
        resp = _jwks_http_get(jwks_url, timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error(
            "[jwks-refresh:%s] JWKS fetch failed (%s) — stale cache continues to serve",
            task_id,
            type(exc).__name__,
        )
        raise  # triggers autoretry

    cache.set(_JWKS_CACHE_KEY, data, timeout=ttl)
    cache.set(_JWKS_STALE_CACHE_KEY, data, timeout=_JWKS_STALE_TTL)
    logger.info("[jwks-refresh:%s] JWKS cache refreshed successfully (ttl=%ds)", task_id, ttl)
