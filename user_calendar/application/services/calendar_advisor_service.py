import json
import logging

from accounts.application.ports.repository import AccountRepository
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException
from user_calendar.application.ports.external.calendar_advisor import (
    CalendarAdvisorPort,
)
from user_calendar.application.ports.repository import CalendarEventRepository
from user_calendar.domain.value_objects import UserId

logger = logging.getLogger(__name__)


class CalendarAdvisorService:
    def __init__(
        self,
        event_repo: CalendarEventRepository,
        account_repo: AccountRepository,
        advisor: CalendarAdvisorPort,
    ):
        self.event_repo = event_repo
        self.account_repo = account_repo
        self.advisor = advisor

    def analyze_document_and_suggest(
        self,
        user_id: UserId,
        document_text: str,
    ) -> str:
        events = self.event_repo.find_by_user_id(user_id)
        account = self.account_repo.find_by_user_id(user_id.value)

        if not account:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)

        if not account.country:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)
        country_context = f"{account.country.code} ({account.country.currency})"

        formatted_events_list = []
        for e in events:
            # explicitly pull out the ID and Title so they are "unmissable"
            formatted_events_list.append(
                f"- EVENT_ID: {e.event_id.value} | TITLE: {e.title} | START: {e.start_at}"
            )

        events_text = "\n".join(formatted_events_list)
        # Call Gemini
        try:
            result = self.advisor.analyze_events(
                events_text=events_text,
                document_text=document_text,
                country_context=country_context,
            )
            logger.debug("Gemini raw output: %s", result)
            return result
        except Exception as e:
            err_msg = str(e)

            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                logger.warning("Gemini quota exceeded. Using fallback advisor.")
                return self._fallback_advice(
                    events_text, document_text, country_context
                )

            logger.error("Gemini error: %s", err_msg)
            return self._fallback_advice(events_text, document_text, country_context)

    def _fallback_advice(
        self, events_text: str, document_text: str, country_context: str
    ) -> str:
        return json.dumps(
            [
                {
                    "event_title": "All events",
                    "suggestion": "keep",
                    "reason": "AI advisor unavailable. No automated changes recommended.",
                }
            ]
        )
