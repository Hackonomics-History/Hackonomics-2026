from news.adapters.orm.models import BusinessNewsModel


class BusinessNewsQueryRepository:

    def get_latest_news(self, country_code: str) -> list[dict]:

        record = (
            BusinessNewsModel.objects.filter(country_code=country_code)
            .order_by("-created_at")
            .first()
        )

        if not record:
            return []

        news_items = record.content or []
        result = []

        for n in news_items:

            result.append(
                {
                    "title": n.get("title", ""),
                    "description": n.get("description", ""),
                    "url": n.get("url"),
                }
            )
        return result
