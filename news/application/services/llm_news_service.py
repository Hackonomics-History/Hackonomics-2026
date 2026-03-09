import logging

from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException

logger = logging.getLogger(__name__)

class LlmNewsService:

    ORDINAL_MAP = {
        "first": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
        "fifth": 4,
    }

    def __init__(
        self,
        account_repo,
        news_repo,
        news_query_repo,
        rag_hybrid,
        rag_rerank,
        llm_adapter,
    ):
        self.account_repo = account_repo
        self.news_repo = news_repo
        self.news_query_repo = news_query_repo
        self.rag_hybrid = rag_hybrid
        self.rag_rerank = rag_rerank
        self.llm_adapter = llm_adapter

    def retrieve_context(self, user_id: str, question: str):

        if not question or not question.strip():
            raise BusinessException(ErrorCode.MISSING_REQUIRED_FIELD)

        account = self.account_repo.find_by_user_id(int(user_id))
        if not account:
            raise BusinessException(ErrorCode.USER_NOT_FOUND)

        country_code = account.country.code
        q = question.lower()

        for word, idx in self.ORDINAL_MAP.items():

            if f"{word} news" in q:
                latest = self.news_query_repo.get_latest_news(country_code)

                if not latest or len(latest) <= idx:
                    raise BusinessException(ErrorCode.DATA_NOT_FOUND)
                return latest[idx: idx + 1]

        candidates = self.rag_hybrid.search(
            question=question,
            country_code=country_code,
            top_k=10,
        )

        if not candidates:
            latest = self.news_query_repo.get_latest_news(country_code)

            if not latest:
                raise BusinessException(ErrorCode.DATA_NOT_FOUND)
            candidates = latest[:5]

        contexts = self.rag_rerank.rerank_news(
            question=question,
            candidates=candidates,
            top_k=3,
        )

        if not contexts:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)
        return contexts

    def ask(self, user_id: str, question: str):
        contexts = self.retrieve_context(user_id, question)

        for c in contexts:
            logger.info(f"RAG CONTEXT: {c}")

        answer = self.llm_adapter.generate(
            question=question,
            contexts=contexts,
        )
        return {
            "answer": answer,
            "sources": contexts,
        }