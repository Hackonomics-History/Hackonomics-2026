from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from news.adapters.orm.models import BusinessNewsDocModel


class BusinessNewsKeywordRepository:
    def search(self, *, country_code: str, query: str, limit: int = 10) -> list[dict]:
        vector = SearchVector("title", weight="A") + SearchVector(
            "description", weight="B"
        )
        q = SearchQuery(query)

        qs = (
            BusinessNewsDocModel.objects.filter(country_code=country_code)
            .annotate(rank=SearchRank(vector, q))
            .filter(rank__gt=0.0)
            .order_by("-rank")[:limit]
        )

        return [
            {
                "title": row.title,
                "description": row.description,
                "url": row.url,
                "_kw_rank": float(row.rank),
            }
            for row in qs
        ]
