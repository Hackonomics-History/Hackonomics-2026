from django.core.management.base import BaseCommand

from authentication.adapters.events.blacklist_sync_consumer import (
    start_blacklist_sync_consumer,
)


class Command(BaseCommand):
    help = "Start the Kafka blacklist-sync consumer (blocks until stopped)"

    def handle(self, *args, **options) -> None:
        self.stdout.write("Starting blacklist-sync Kafka consumer…")
        start_blacklist_sync_consumer()
