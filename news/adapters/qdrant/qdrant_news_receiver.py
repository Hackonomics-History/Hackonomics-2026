from django.conf import settings
from news.adapters.embedding.fastembed_embedder import embed_text
from qdrant_client import QdrantClient


class NewsRetriever:

    def __init__(self):
        self.qdrant = QdrantClient(url=settings.QDRANT_URL)

    def search(self, query: str, limit: int = 5):

        vector = embed_text(query)

        results = self.qdrant.search(
            collection_name=settings.QDRANT_COLLECTION_NEWS,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )

        return [r.payload for r in results]