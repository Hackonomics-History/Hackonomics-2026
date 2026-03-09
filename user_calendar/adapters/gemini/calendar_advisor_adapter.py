import time

from django.conf import settings
from google import genai
from google.genai import types

from user_calendar.application.ports.external.calendar_advisor import (
    CalendarAdvisorPort,
)


class GeminiCalendarAdvisorAdapter(CalendarAdvisorPort):
    MAX_EVENTS = 10
    MODEL_NAME = settings.GEMINI_MODEL

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def analyze_events(
        self,
        events_text: str,
        document_text: str,
        country_context: str,
    ) -> str:
        prompt = f"""
        COUNTRY CONTEXT: {country_context}

        USER'S CALENDAR EVENTS:
        {events_text}

        NEWS ARTICLE / DOCUMENT:
        {document_text}

        TASK:
        1. Identify EVERY event in the list above that could be impacted by the news.
        2. If multiple events share the same impact. you MUST group all their IDs together.
        3. Return a JSON array where each item follows this format exactly:

        [
        {{
            "title": "<Short Impact Summary>",
            "description": "<Why this matters for these specific events>",
            "event_ids": ["ID1", "ID2", "ID3"],
            "priority": "HIGH | MEDIUM | LOW"
        }}
        ]

        CRITICAL RULES:
        - DO NOT be lazy. If 5 events are related, include all 5 IDs in the "event_ids" array.
        - If no events are related, return an empty array [].
        """

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        )

        max_retries = 3
        delay = 5

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=prompt,
                    config=config,
                )
                return response.text

            except Exception as e:
                if "429" in str(e) or "503" in str(e):
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue
                raise e

        return "[]"
