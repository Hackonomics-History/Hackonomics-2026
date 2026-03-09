from __future__ import annotations

from typing import Any, Dict, List

from news.adapters.rerank.fastembed_reranker import FastEmbedReranker, RerankItem


class NewsRagRerankService:
    def __init__(self, reranker: FastEmbedReranker):
        self.reranker = reranker

    def rerank_news(
        self,
        question: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        items = [
            RerankItem(
                title=str(c.get("title", "")),
                description=str(c.get("description", "")),
                url=c.get("url"),
            )
            for c in candidates
        ]

        top = self.reranker.rerank(question, items, top_k=top_k)
        out: List[Dict[str, Any]] = []
        for it in top:
            out.append(
                {
                    "title": it.title,
                    "description": it.description,
                    "url": it.url,
                }
            )
        return out
