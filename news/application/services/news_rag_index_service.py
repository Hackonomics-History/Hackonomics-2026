import logging
from django.conf import settings
from django.db import transaction
from qdrant_client.http.models import Distance, VectorParams

from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from news.adapters.orm.models import BusinessNewsDocModel

logger = logging.getLogger(__name__)

class NewsRagIndexService:

    def __init__(self, query_repo, qdrant_indexer):
        self.query_repo = query_repo
        self.qdrant_indexer = qdrant_indexer
        self.qdrant = qdrant_indexer.qdrant

    def _ensure_collection(self, vector_size: int):

        collections = [c.name for c in self.qdrant.get_collections().collections]

        if settings.QDRANT_COLLECTION_NEWS not in collections:

            self.qdrant.create_collection(
                collection_name=settings.QDRANT_COLLECTION_NEWS,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

    @transaction.atomic
    def index_latest_country_news(self, country_code: str) -> None:

        news_items = self.query_repo.get_latest_news(country_code)

        if not news_items:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)

        news_items = news_items[:10]

        BusinessNewsDocModel.objects.filter(country_code=country_code).delete()

        docs = []

        for n in news_items:

            docs.append(
                BusinessNewsDocModel(
                    country_code=country_code,
                    title=n.get("title", ""),
                    description=n.get("description", ""),
                    url=n.get("url"),
                )
            )

        BusinessNewsDocModel.objects.bulk_create(docs)

        try:
            from news.adapters.embedding.fastembed_embedder import embed_texts

            vec = embed_texts(["ping"])[0]

            self._ensure_collection(len(vec))

            self.qdrant_indexer.upsert(
                country_code=country_code,
                news_items=news_items,
            )

        except Exception as e:
            logger.exception("Vector indexing failed")
            raise BusinessException(ErrorCode.SERVICE_UNAVAILABLE)
