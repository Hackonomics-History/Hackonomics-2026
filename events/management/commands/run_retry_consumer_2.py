from django.core.management.base import BaseCommand

from events.consumers.retry_consumer import RetryConsumer


class Command(BaseCommand):
    help = "Retry consumer tier 2 — user-activities.retry-2 (delay: 300 s)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Retry Consumer 2..."))
        RetryConsumer(
            topic="user-activities.retry-2",
            group_id="accounts-service-retry-2",
            delay_ms=300_000,
        ).run()
