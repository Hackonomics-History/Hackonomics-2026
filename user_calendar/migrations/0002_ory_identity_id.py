from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user_calendar", "0001_initial"),
    ]

    operations = [
        # ── UserCalendarModel ────────────────────────────────────────────────
        migrations.AddField(
            model_name="usercalendarmodel",
            name="ory_identity_id",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="usercalendarmodel",
            name="user_id",
            field=models.IntegerField(blank=True, null=True, unique=True),
        ),
        # ── CategoryModel ────────────────────────────────────────────────────
        migrations.AddField(
            model_name="categorymodel",
            name="ory_identity_id",
            field=models.CharField(blank=True, db_index=True, max_length=128, null=True),
        ),
        migrations.AlterField(
            model_name="categorymodel",
            name="user_id",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
        # ── CalendarEventModel ───────────────────────────────────────────────
        migrations.AddField(
            model_name="calendareventmodel",
            name="ory_identity_id",
            field=models.CharField(blank=True, db_index=True, max_length=128, null=True),
        ),
        migrations.AlterField(
            model_name="calendareventmodel",
            name="user_id",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
    ]
