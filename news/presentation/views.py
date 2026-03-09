from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from news.application.factories.business_news_service_factory import (
    build_business_news_service,
)
from news.application.factories.llm_news_service_factory import (
    build_llm_news_service,
)
from news.tasks import fetch_business_news
from user_calendar.domain.value_objects import UserId


class BusinessNewsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = build_business_news_service()

        data = service.get_user_business_news(UserId(request.user.id))

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


class BusinessNewsRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        service = build_business_news_service()

        country_code = service.refresh_user_country_news(UserId(request.user.id))

        async_result = fetch_business_news.delay(
            country_code,
            True,
        )

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
        service = build_llm_news_service()
        result = service.ask(
            user_id=str(request.user.id),
            question=question,
        )

        def event_stream():
            answer = result["answer"]

            yield f"data: {answer} \n\n"
            yield "data: done\n\n"

        return StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )