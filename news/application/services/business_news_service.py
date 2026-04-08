import logging
from datetime import timedelta
from typing import Optional

import sentry_sdk
from babel import Locale
from django.core.cache import cache
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from accounts.application.ports.repository import AccountRepository
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from news.adapters.orm.models import NewsTaskState
from news.application.ports.business_news_port import BusinessNewsPort
from news.application.ports.business_news_repository import BusinessNewsRepository
from news.domain.entities import BusinessNews
from user_calendar.domain.value_objects import UserId

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 6
UPDATE_INTERVAL_HOURS = 6


class BusinessNewsService:
    def __init__(
        self,
        account_repo: AccountRepository,
        news_port: BusinessNewsPort,
        news_repo: BusinessNewsRepository,
    ):
        self.account_repo = account_repo
        self.news_port = news_port
        self.news_repo = news_repo

    def get_user_business_news(self, user_id: UserId) -> dict:
        country_code = self._get_country_code_or_none(user_id)
        if not country_code:
            return self._empty_response()

        cache_key = self._cache_key(country_code)

        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit → {country_code}")
            return cached

        latest = self.news_repo.find_latest(country_code)
        if not latest:
            return self._empty_response(country_code)

        response = self._build_response(latest)
        cache.set(cache_key, response, CACHE_TTL)

        return response

    def refresh_user_country_news(self, user_id: UserId) -> str:
        return self._get_country_code_or_raise(user_id)

    def fetch_and_store_news(
        self,
        country_code: str,
        force: bool = False,
        task_id: Optional[str] = None,
    ) -> None:
        """Fetch and persist news for a country with atomic DB-level locking.

        Locking strategy (two-tier):
        1. select_for_update(nowait=True) on NewsTaskState acquires an exclusive
           DB row lock. If another worker holds the lock, we skip immediately
           rather than queue (OperationalError with nowait=True).
        2. Double-check last_run_at after acquiring the lock — a prior worker
           may have already completed the fetch between task dispatch and lock
           acquisition. If the data is still fresh we abort without calling
           the Gemini API, preventing duplicate paid API calls.

        The DB lock is released before the Gemini API call (outside transaction)
        so we never hold a DB row lock across a slow external HTTP request.
        """
        try:
            should_run = self._acquire_lock_and_check(country_code, force, task_id)
        except OperationalError:
            # Another worker holds the lock — skip gracefully.
            logger.info("Skip %s: DB lock held by another worker (task_id=%s)", country_code, task_id)
            return

        if not should_run:
            return  # double-check determined data is fresh

        # ── Gemini API call (outside transaction, lock already released) ──────
        logger.info("Fetching news → %s (force=%s, task_id=%s)", country_code, force, task_id)
        try:
            news_items = self.news_port.get_country_news(country_code)
        except Exception as exc:
            logger.exception("Gemini fetch raised unexpectedly (%s): %s", country_code, exc)
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("failed_service", "gemini")
                scope.set_tag("country_code", country_code)
                scope.set_extra("task_id", task_id)
                sentry_sdk.capture_exception(exc)
            return

        if not news_items:
            logger.warning("No valid news returned → %s", country_code)
            return

        now = timezone.now()
        news = BusinessNews(country_code=country_code, content=news_items, created_at=now)
        try:
            with transaction.atomic():
                self.news_repo.save(news)
                NewsTaskState.objects.filter(country_code=country_code).update(last_run_at=now)
        except IntegrityError:
            logger.warning(
                "Concurrent insert detected for %s — skipping duplicate save (task_id=%s)",
                country_code,
                task_id,
            )
            return

        response = self._build_response(news)
        cache.set(self._cache_key(country_code), response, CACHE_TTL)
        logger.info("News updated → %s", country_code)

    def _acquire_lock_and_check(
        self,
        country_code: str,
        force: bool,
        task_id: Optional[str],
    ) -> bool:
        """Acquire select_for_update lock and perform double-check.

        Returns True  → caller should proceed with the Gemini API call.
        Returns False → caller should abort (data still fresh).
        Raises OperationalError → lock contention (nowait=True, skip).
        """
        with transaction.atomic():
            state, _ = NewsTaskState.objects.select_for_update(nowait=True).get_or_create(
                country_code=country_code
            )

            if state.last_run_at and not force:
                age = timezone.now() - state.last_run_at
                if age < timedelta(hours=UPDATE_INTERVAL_HOURS):
                    logger.info(
                        "Abort %s: double-check shows fresh data (age=%s, task_id=%s)",
                        country_code,
                        age,
                        task_id,
                    )
                    sentry_sdk.add_breadcrumb(
                        category="task.atomicity",
                        message=f"News task aborted (double-check fresh): {country_code}",
                        level="info",
                        data={
                            "abort_reason": "double_check_fresh",
                            "country_code": country_code,
                            "task_id": task_id,
                            "data_age_seconds": age.total_seconds(),
                        },
                    )
                    return False

            # Stamp last_run_at now so concurrent workers see "in-flight" immediately.
            state.last_run_at = timezone.now()
            state.save(update_fields=["last_run_at"])
            return True

    # Helpers
    def _get_country_code_or_raise(self, user_id: UserId) -> str:
        account = self.account_repo.find_by_user_id(user_id.value)
        if not account or not account.country:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)
        return account.country.code

    def _get_country_code_or_none(self, user_id: UserId) -> str | None:
        account = self.account_repo.find_by_user_id(user_id.value)
        if not account or not account.country:
            return None
        return account.country.code

    def _get_country_name(self, code: str | None) -> str | None:
        if not code:
            return None

        try:
            return Locale("en").territories.get(code.upper(), code)
        except Exception:
            return code

    def _is_fresh(self, news: BusinessNews) -> bool:
        age = timezone.now() - news.created_at
        return age < timedelta(hours=UPDATE_INTERVAL_HOURS)

    def _build_response(self, news: BusinessNews) -> dict:
        next_update = news.created_at + timedelta(hours=UPDATE_INTERVAL_HOURS)

        return {
            "country_code": news.country_code,
            "country_name": self._get_country_name(news.country_code),
            "news": news.content,
            "last_updated": news.created_at,
            "next_update": next_update,
            "update_interval_hours": UPDATE_INTERVAL_HOURS,
        }

    def _empty_response(
        self,
        country_code: str | None = None,
    ) -> dict:
        return {
            "country_code": country_code,
            "country_name": self._get_country_name(country_code),
            "news": [],
            "last_updated": None,
            "next_update": None,
            "update_interval_hours": UPDATE_INTERVAL_HOURS,
        }

    def _cache_key(self, country_code: str) -> str:
        return f"business_news:{country_code}"
