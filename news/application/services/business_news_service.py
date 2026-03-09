import logging
from datetime import timedelta

from babel import Locale
from django.core.cache import cache
from django.utils import timezone

from accounts.application.ports.repository import AccountRepository
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from news.application.ports.business_news_port import BusinessNewsPort
from news.application.ports.business_news_repository import BusinessNewsRepository
from news.domain.entities import BusinessNews
from user_calendar.domain.value_objects import UserId

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 6
LOCK_TTL = 60 * 10
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
    ) -> None:
        lock_key = self._lock_key(country_code)

        if not cache.add(lock_key, "locked", timeout=LOCK_TTL):
            logger.info(f"Skip {country_code}: another worker updating")
            return

        try:
            latest = self.news_repo.find_latest(country_code)

            if latest and self._is_fresh(latest) and not force:
                logger.info(f"Skip {country_code}: still fresh")
                return

            logger.info(f"Fetching news → {country_code} (force={force})")

            news_items = self.news_port.get_country_news(country_code)

            if not news_items:
                logger.warning(f"No valid news returned → {country_code}")
                return

            news = BusinessNews(
                country_code=country_code,
                content=news_items,
                created_at=timezone.now(),
            )

            self.news_repo.save(news)

            response = self._build_response(news)
            cache.set(self._cache_key(country_code), response, CACHE_TTL)

            logger.info(f"News updated → {country_code}")

        except Exception as e:
            logger.exception(f"News fetch failed ({country_code}): {e}")

        finally:
            cache.delete(lock_key)

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

    def _lock_key(self, country_code: str) -> str:
        return f"news-lock:{country_code}"
