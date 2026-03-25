from django.core.management.base import BaseCommand

from accounts.adapters.events.kafka_consumer import start_kafka_consumer


class Command(BaseCommand):
    help = "Run Kafka consumer for the accounts service (at-least-once, manual commit)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Accounts Kafka Consumer..."))
        start_kafka_consumer()
