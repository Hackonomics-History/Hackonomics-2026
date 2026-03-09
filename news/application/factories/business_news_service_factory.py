from accounts.adapters.orm.repository import DjangoAccountRepository
from news.adapters.gemini.business_news_adapter import GeminiBusinessNewsAdapter
from news.adapters.orm.repository import DjangoBusinessNewsRepository
from news.application.services.business_news_service import BusinessNewsService


def build_business_news_service() -> BusinessNewsService:
    return BusinessNewsService(
        account_repo=DjangoAccountRepository(),
        news_port=GeminiBusinessNewsAdapter(),
        news_repo=DjangoBusinessNewsRepository(),
    )
