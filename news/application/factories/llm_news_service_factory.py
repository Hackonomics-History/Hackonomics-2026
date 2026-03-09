from news.adapters.embedding.fastembed_embedder import embed_text
from news.adapters.orm.repository import DjangoBusinessNewsRepository
from news.adapters.business_news_keyword_repository import BusinessNewsKeywordRepository
from news.adapters.business_news_query_repository import BusinessNewsQueryRepository
from news.adapters.qdrant.qdrant_client import get_qdrant
from news.adapters.rerank.fastembed_reranker import FastEmbedReranker
from news.adapters.gemini.gemini_chat_adapter import GeminiChatAdapter
from news.application.services.llm_news_service import LlmNewsService
from news.application.services.news_rag_hybrid_service import NewsRagHybridService
from news.application.services.news_rag_query_service import NewsRagQueryService
from news.application.services.news_rag_rerank_service import NewsRagRerankService

from accounts.adapters.orm.repository import DjangoAccountRepository


def build_llm_news_service():

    account_repo = DjangoAccountRepository()
    news_repo = DjangoBusinessNewsRepository()
    news_query_repo = BusinessNewsQueryRepository()

    vec_repo = NewsRagQueryService(
        qdrant=get_qdrant(),
        embedder=embed_text,
    )

    kw_repo = BusinessNewsKeywordRepository()

    hybrid = NewsRagHybridService(vec_repo=vec_repo, kw_repo=kw_repo)
    rerank = NewsRagRerankService(reranker=FastEmbedReranker())

    llm_adapter = GeminiChatAdapter()

    return LlmNewsService(
        account_repo=account_repo,
        news_repo=news_repo,
        news_query_repo=news_query_repo,
        rag_hybrid=hybrid,
        rag_rerank=rerank,
        llm_adapter=llm_adapter,
    )