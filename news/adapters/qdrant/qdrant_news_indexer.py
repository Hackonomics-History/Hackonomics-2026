from django.conf import settings
from qdrant_client.http.models import PointStruct

from news.adapters.embedding.fastembed_embedder import embed_texts
from news.adapters.qdrant.qdrant_client import get_qdrant


class QdrantNewsIndexer:

    def __init__(self):
        self.qdrant = get_qdrant()

    def upsert(self, *, country_code: str, news_items: list[dict]):

        texts = []

        for n in news_items:
            title = n.get("title", "")
            desc = n.get("description", "")

            texts.append(f"{title}\n{desc}")

        vectors = embed_texts(texts)

        points = []

        for i, n in enumerate(news_items):

            points.append(
                PointStruct(
                    id=hash(n.get("url")),
                    vector=vectors[i],
                    payload={
                        "country_code": country_code,
                        "title": n.get("title", ""),
                        "description": n.get("description", ""),
                        "url": n.get("url"),
                    },
                )
            )

        self.qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION_NEWS,
            points=points,
        )
