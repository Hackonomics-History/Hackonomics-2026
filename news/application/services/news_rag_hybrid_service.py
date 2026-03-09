from collections import defaultdict


class NewsRagHybridService:
    def __init__(self, vec_repo, kw_repo):
        self.vec_repo = vec_repo
        self.kw_repo = kw_repo

    def _key(self, item: dict) -> str:
        if item.get("url"):
            return f"url::{item['url']}"
        return f"td::{item.get('title', '')}::{item.get('description', '')[:80]}"

    def _rrf(self, ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
        scores = defaultdict(float)
        items = {}

        for lst in ranked_lists:
            for rank, item in enumerate(lst, start=1):
                key = self._key(item)
                items[key] = item
                scores[key] += 1.0 / (k + rank)

        merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for key, s in merged:
            obj = dict(items[key])
            obj["_hybrid_score"] = float(s)
            results.append(obj)
        return results

    def search(self, *, question: str, country_code: str, top_k: int = 3) -> list[dict]:
        vec = self.vec_repo.search(
            question=question, country_code=country_code, top_k=10
        )
        kw = self.kw_repo.search(country_code=country_code, query=question, limit=10)

        fused = self._rrf([vec, kw], k=60)

        cleaned = []
        for x in fused[:top_k]:
            cleaned.append(
                {
                    "title": x.get("title", ""),
                    "description": x.get("description", ""),
                    "url": x.get("url"),
                }
            )
        return cleaned
