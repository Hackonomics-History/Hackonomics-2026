import requests
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.adapters.orm.repository import DjangoAccountRepository
from news.adapters.gemini.business_news_adapter import GeminiBusinessNewsAdapter
from news.adapters.orm.repository import DjangoBusinessNewsRepository
from news.application.services.business_news_service import BusinessNewsService
from news.application.services.llm_news_service import LlmNewsService
from news.tasks import fetch_business_news
from user_calendar.domain.value_objects import UserId


def _build_service() -> BusinessNewsService:
    return BusinessNewsService(
        account_repo=DjangoAccountRepository(),
        news_port=GeminiBusinessNewsAdapter(),
        news_repo=DjangoBusinessNewsRepository(),
    )

def _build_llm_news_service() -> LlmNewsService:
    return LlmNewsService()

class BusinessNewsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = _build_service()
        data = service.get_user_business_news(UserId(request.user.id))
        return Response(data, status=status.HTTP_200_OK)


class BusinessNewsRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        service = _build_service()
        country_code = service.refresh_user_country_news(
            UserId(request.user.id)
        )

        async_result = fetch_business_news.delay(country_code, True)

        return Response(
            {
                "status": "queued",
                "country_code": country_code,
                "task_id": async_result.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )

class ChatStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        question = request.data.get("question")

        account_repo = DjangoAccountRepository()
        account = account_repo.find_by_user_id(request.user.id)

        country_code = account.country.code

        service = _build_llm_news_service()

        payload = service.prepare_llm_payload(
            user_id=str(request.user.id),
            question=question,
            country_code=country_code,
        )

        response = requests.post(
            settings.LLM_SERVICE_URL,
            json=payload,
            stream=True,
            timeout=300,
        )

        def event_stream():
            for chunk in response.iter_content(
                chunk_size=None,
                decode_unicode=True,
            ):
                if chunk:
                    yield chunk

        return StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )