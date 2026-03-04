from news.adapters.business_news_repository import BusinessNewsRepository

from common.errors.exceptions import BusinessException
from common.errors.error_codes import ErrorCode

class LlmNewsService:

    def __init__(self):
        self.repo = BusinessNewsRepository()

    def prepare_llm_payload(
        self,
        user_id: str,
        question: str,
        country_code: str,
    ):

        if not question:
            raise BusinessException(ErrorCode.MISSING_REQUIRED_FIELD)

        news = self.repo.get_latest_news(country_code)
        print("COUNTRY:", country_code)
        print("NEWS:", news)

        if not news:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)

        # reduce tokens for LLM
        news = news[:3]

        return {
            "user_id": user_id,
            "question": question,
            "news": news,
        }