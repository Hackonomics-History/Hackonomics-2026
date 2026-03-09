from django.db import models


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
