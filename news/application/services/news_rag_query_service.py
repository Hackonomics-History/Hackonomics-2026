from qdrant_client.http.models import FieldCondition, Filter, MatchValue


class NewsRagQueryService:
    def __init__(self, qdrant, embedder):
        self.qdrant = qdrant
        self.embedder = embedder

    def search(
        self, *, question: str, country_code: str, top_k: int = 10
    ) -> list[dict]:
        vec = self.embedder(question)

        flt = Filter(
            must=[
                FieldCondition(
                    key="country_code", match=MatchValue(value=country_code)
                ),
            ]
        )

        result = self.qdrant.query_points(
            collection_name="business_news",
            query=vec,
            query_filter=flt,
            limit=top_k,
            with_payload=True,
        )

        out = []
        for h in result.points:
            p = h.payload or {}
            out.append(
                {
                    "title": p.get("title", ""),
                    "description": p.get("description", ""),
                    "url": p.get("url"),
                    "_vec_score": float(h.score),
                }
            )
        return out
