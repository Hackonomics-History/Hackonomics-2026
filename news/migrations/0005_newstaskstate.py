# Generated migration for NewsTaskState

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0004_businessnewsdocmodel"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsTaskState",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "country_code",
                    models.CharField(db_index=True, max_length=10, unique=True),
                ),
                (
                    "last_run_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        help_text="Timestamp of the last completed Gemini fetch for this country.",
                    ),
                ),
            ],
            options={
                "db_table": "news_task_state",
            },
        ),
    ]
