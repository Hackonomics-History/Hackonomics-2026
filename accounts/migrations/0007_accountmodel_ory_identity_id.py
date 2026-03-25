from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_remove_accountmodel_email"),
    ]

    operations = [
        # Add Ory identity column (nullable until backfill is complete)
        migrations.AddField(
            model_name="accountmodel",
            name="ory_identity_id",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
        # Make legacy integer user_id nullable so new rows can omit it
        migrations.AlterField(
            model_name="accountmodel",
            name="user_id",
            field=models.IntegerField(blank=True, null=True, unique=True),
        ),
    ]
