from news.adapters.orm.models import BusinessNewsModel


class BusinessNewsRepository:

    def get_latest_news(self, country_code: str):
        record = (
            BusinessNewsModel.objects
            .filter(country_code=country_code)
            .order_by("-created_at")
            .first()
        )

        return record.content if record else []