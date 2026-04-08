from django.core.management.base import BaseCommand

from events.consumers.retry_consumer import RetryConsumer


class Command(BaseCommand):
    help = "Retry consumer tier 1 — user-activities.retry-1 (delay: 60 s)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Retry Consumer 1..."))
        RetryConsumer(
            topic="user-activities.retry-1",
            group_id="accounts-service-retry-1",
            delay_ms=60_000,
        ).run()
