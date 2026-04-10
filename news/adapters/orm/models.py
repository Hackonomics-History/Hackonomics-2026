from django.db import models


class NewsTaskState(models.Model):
    """Per-country atomic task gate for the news collection worker.

    Used with select_for_update() to provide a DB-level distributed lock that
    survives Redis outages. A row is created on first run and updated every
    successful fetch, giving workers a reliable double-check timestamp.
    """

    country_code = models.CharField(max_length=10, unique=True, db_index=True)
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last completed Gemini fetch for this country.",
    )

    class Meta:
        db_table = "news_task_state"

    def __str__(self) -> str:
        return f"NewsTaskState({self.country_code}, last_run={self.last_run_at})"


class BusinessNewsModel(models.Model):
    country_code = models.CharField(max_length=10, db_index=True)
    content = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "business_news"
        ordering = ["-created_at"]


class BusinessNewsDocModel(models.Model):
    country_code = models.CharField(max_length=10, db_index=True)
    title = models.TextField()
    description = models.TextField()
    url = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "business_news_doc"
