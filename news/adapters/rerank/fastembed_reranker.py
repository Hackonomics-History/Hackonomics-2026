from __future__ import annotations
from dataclasses import dataclass
from typing import List, Sequence
from django.conf import settings

try:
    from fastembed.rerank.cross_encoder import TextCrossEncoder
except Exception:  # pragma: no cover
    TextCrossEncoder = None  # type: ignore


@dataclass(frozen=True)
class RerankItem:
    title: str
    description: str
    url: str | None = None


class FastEmbedReranker:
    _model = None

    def _get_model(self):

        if TextCrossEncoder is None:
            raise RuntimeError(
                "FastEmbed reranker is not available. "
                "Please upgrade fastembed."
            )

        if FastEmbedReranker._model is None:
            FastEmbedReranker._model = TextCrossEncoder(
                model_name=settings.RERANK_MODEL_NAME
            )

        return FastEmbedReranker._model

    def rerank(
        self,
        query: str,
        items: Sequence[RerankItem],
        top_k: int = 3,
    ) -> List[RerankItem]:

        if not items:
            return []

        model = self._get_model()

        docs = [
            f"{it.title}\n{it.description}".strip()
            for it in items
        ]

        results = model.rerank(query, docs)

        ranked = sorted(
            zip(items, results),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        return [it for it, _ in ranked[:top_k]]