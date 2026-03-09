from google import genai
from django.conf import settings


class GeminiChatAdapter:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    def generate(self, question: str, contexts: list[dict]) -> str:
        context_text = "\n\n".join(
            f"{c['title']}\n{c['description']}"
            for c in contexts
        )

        prompt = f"""
            You are a financial news assistant.

            Use ONLY the provided news article to answer the question.
            Do NOT add outside knowledge.
            If the answer is not in the article, say:
            "I cannot find this information in the news."

            News article:
            {context_text}

            Question:
            {question}

            Instructions:
            - Explain in simple English.
            - Use short sentences.
            - Use proper spacing between words.
            - Write 3–4 sentences maximum.
            - Do not repeat the article title.
            - Do not add information not in the article.

            Answer:
        """

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text