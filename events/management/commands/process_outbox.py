from django.core.management.base import BaseCommand

from events.consumers.outbox_to_kafka import run_worker


class Command(BaseCommand):
    help = "Relay unpublished OutboxEvent records to Kafka (at-least-once, batch=100)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Outbox Worker..."))
        run_worker()
