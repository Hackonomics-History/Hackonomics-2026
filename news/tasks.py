import logging
from typing import Optional

from celery import shared_task

from accounts.adapters.orm.repository import DjangoAccountRepository
from news.adapters.business_news_query_repository import BusinessNewsQueryRepository
from news.adapters.gemini.business_news_adapter import GeminiBusinessNewsAdapter
from news.adapters.orm.repository import DjangoBusinessNewsRepository
from news.adapters.qdrant.qdrant_news_indexer import QdrantNewsIndexer
from news.application.services.business_news_service import BusinessNewsService
from news.application.services.news_rag_index_service import NewsRagIndexService

logger = logging.getLogger(__name__)


def _build_services():

    account_repo = DjangoAccountRepository()
    news_repo = DjangoBusinessNewsRepository()
    query_repo = BusinessNewsQueryRepository()

    news_service = BusinessNewsService(
        account_repo=account_repo,
        news_port=GeminiBusinessNewsAdapter(),
        news_repo=news_repo,
    )

    rag_service = NewsRagIndexService(
        query_repo=query_repo,
        qdrant_indexer=QdrantNewsIndexer(),
    )

    return news_service, rag_service


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, RuntimeError),
    retry_backoff=60,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
)
def fetch_business_news(
    self,
    country_code: Optional[str] = None,
    force: bool = False,
) -> None:

    task_id = getattr(self.request, "id", None)

    news_service, rag_service = _build_services()

    if country_code:

        logger.info(
            "[task:%s] manual refresh start → %s (force=%s)",
            task_id,
            country_code,
            force,
        )

        news_service.fetch_and_store_news(
            country_code,
            force=force,
        )

        rag_service.index_latest_country_news(country_code)

        logger.info(
            "[task:%s] manual refresh completed → %s",
            task_id,
            country_code,
        )
        return

    countries = news_service.account_repo.get_all_country_codes()

    if not countries:

        logger.info(
            "[task:%s] no countries found — skipping",
            task_id,
        )
        return

    logger.info(
        "[task:%s] scheduled refresh start — %d countries",
        task_id,
        len(countries),
    )

    for code in countries:
        try:
            news_service.fetch_and_store_news(code)
            rag_service.index_latest_country_news(code)
        except Exception:
            logger.exception(
                "[task:%s] failed refreshing %s",
                task_id,
                code,
            )
    logger.info(
        "[task:%s] scheduled refresh completed",
        task_id,
    )
