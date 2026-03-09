from django.conf import settings
from qdrant_client import QdrantClient


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL)
