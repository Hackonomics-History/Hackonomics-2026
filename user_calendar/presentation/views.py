import json
import logging
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.adapters.orm.repository import DjangoAccountRepository
from common.errors.exceptions import BusinessException
from user_calendar.adapters.gemini.calendar_advisor_adapter import (
    GeminiCalendarAdvisorAdapter,
)
from user_calendar.adapters.orm.repository import (
    DjangoCalendarEventRepository,
    DjangoCategoryRepository,
    DjangoUserCalendarRepository,
)
from user_calendar.application.services.calendar_advisor_service import (
    CalendarAdvisorService,
)
from user_calendar.application.services.calendar_event_service import (
    CalendarEventService,
)
from user_calendar.application.services.category_service import CategoryService
from user_calendar.application.services.user_calendar_service import UserCalendarService
from user_calendar.domain.value_objects import CategoryId, EventId, UserId
from user_calendar.presentation.serializers import (
    CalendarEventCreateSerializer,
    CalendarEventSerializer,
    CategoryCreateSerializer,
    CategorySerializer,
    UserCalendarSerializer,
)
from user_calendar.utils.google_oauth import build_google_calendar_flow

logger = logging.getLogger(__name__)


def _build_calendar_event_service() -> CalendarEventService:
    return CalendarEventService(
        event_repo=DjangoCalendarEventRepository(),
        category_repo=DjangoCategoryRepository(),
    )


class UserCalendarInitAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        service = UserCalendarService(DjangoUserCalendarRepository())
        calendar = service.get_or_create_calendar_for_user(UserId(request.user.ory_id))
        serializer = UserCalendarSerializer.from_domain(calendar)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GoogleCalendarOAuthLoginAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        flow = build_google_calendar_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true"
        )
        # Save state in session
        request.session["google_calendar_oauth_state"] = state

        return Response({"redirect_url": authorization_url})


class GoogleCalendarOAuthCallbackAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = request.session.get("google_calendar_oauth_state")

        flow = build_google_calendar_flow(state)

        authorization_response = request.build_absolute_uri()
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials

        service = UserCalendarService(DjangoUserCalendarRepository())
        # Stored tokens in UserCalendar
        existing_calendar = service.get_calendar(UserId(request.user.ory_id))
        calendar = service.connect_google_calendar(
            user_id=UserId(request.user.ory_id),
            google_calendar_id="primary",  # Default calendar
            access_token=credentials.token,
            refresh_token=credentials.refresh_token or existing_calendar.refresh_token,
        )
        serializer = UserCalendarSerializer.from_domain(calendar)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyCalendarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = UserCalendarService(DjangoUserCalendarRepository())
        calendar = service.get_calendar(UserId(request.user.ory_id))
        serializer = UserCalendarSerializer.from_domain(calendar)

        return Response(serializer.data, status=status.HTTP_200_OK)


# Categories
class CategoryCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CategoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = CategoryService(DjangoCategoryRepository())

        category = service.create_category(
            user_id=UserId(request.user.ory_id),
            name=serializer.validated_data["name"],
            color=serializer.validated_data.get("color"),
        )

        response = CategorySerializer.from_domain(category)
        return Response(response.data, status=status.HTTP_201_CREATED)


class CategoryListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = CategoryService(DjangoCategoryRepository())
        categories = service.list_categories(UserId(request.user.ory_id))
        data = [CategorySerializer.from_domain(c).data for c in categories]

        return Response(data, status=status.HTTP_200_OK)


class CategoryDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, category_id: UUID):
        service = CategoryService(DjangoCategoryRepository())
        service.delete_category(
            CategoryId(category_id),
            UserId(request.user.ory_id),
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


# Calendar Events
class CalendarEventCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CalendarEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = _build_calendar_event_service()

        event = service.create_event(
            user_id=UserId(request.user.ory_id),
            title=serializer.validated_data["title"],
            start_at=serializer.validated_data["start_at"],
            end_at=serializer.validated_data["end_at"],
            estimated_cost=serializer.validated_data.get("estimated_cost"),
            category_ids=serializer.validated_data.get("category_ids", []),
        )

        response = CalendarEventSerializer.from_domain(event)
        return Response(response.data, status=status.HTTP_201_CREATED)


class CalendarEventListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = _build_calendar_event_service()
        events = service.list_events(UserId(request.user.ory_id))
        data = [CalendarEventSerializer.from_domain(e).data for e in events]
        return Response(data, status=status.HTTP_200_OK)


class CalendarEventDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, event_id: UUID):
        serializer = CalendarEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = _build_calendar_event_service()

        service.update_event(
            event_id=EventId(event_id),
            user_id=UserId(request.user.ory_id),
            title=serializer.validated_data["title"],
            start_at=serializer.validated_data["start_at"],
            end_at=serializer.validated_data["end_at"],
            estimated_cost=serializer.validated_data.get("estimated_cost"),
            category_ids=serializer.validated_data.get("category_ids", []),
        )

        return Response(status=status.HTTP_200_OK)

    def delete(self, request, event_id: UUID):
        service = _build_calendar_event_service()

        service.delete_event(
            EventId(event_id),
            user_id=UserId(request.user.ory_id),
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class CalendarAdviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_text = request.data.get("document_text")

        service = CalendarAdvisorService(
            event_repo=DjangoCalendarEventRepository(),
            account_repo=DjangoAccountRepository(),
            advisor=GeminiCalendarAdvisorAdapter(),
        )

        try:
            raw_advice = service.analyze_document_and_suggest(
                user_id=UserId(request.user.ory_id),
                document_text=document_text,
            )

            try:
                advice_data = json.loads(raw_advice)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Gemini returned invalid JSON: {raw_advice}")
                return Response(
                    {"error": "AI response was malformed. Please try again."},
                    status=status.HTTP_424_FAILED_DEPENDENCY,
                )

            return Response({"advice": advice_data}, status=status.HTTP_200_OK)

        except BusinessException:
            raise
        except Exception as e:
            logger.error(f"CalendarAdvisorService Error: {str(e)}")
            return Response(
                {
                    "error": "The AI advisor is currently unavailable. Please try again in a few minutes."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
