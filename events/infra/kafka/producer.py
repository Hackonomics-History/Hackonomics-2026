import json
import logging

from confluent_kafka import Producer
from django.conf import settings
from prometheus_client import Counter

logger = logging.getLogger(__name__)

kafka_produced_total = Counter(
    "django_kafka_produced_total",
    "Total Kafka messages produced",
    ["status"],  # labels: success | failure
)


class KafkaEventProducer:
    """confluent-kafka producer with at-least-once delivery semantics.

    publish() blocks until the broker acknowledges the message (flush).
    Returns True only when the delivery callback fires without error.
    The caller must NOT mark the event as published until True is returned.
    """

    def __init__(self):
        self._producer = Producer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "delivery.timeout.ms": 10000,  # 10 s max per message
            }
        )

    def publish(self, topic: str, event: dict) -> bool:
        delivery_result: dict = {"success": False}

        def _on_delivery(err, msg):
            if err:
                kafka_produced_total.labels(status="failure").inc()
                logger.error(
                    "Kafka delivery failed [topic=%s]: %s", topic, err
                )
            else:
                kafka_produced_total.labels(status="success").inc()
                delivery_result["success"] = True

        try:
            self._producer.produce(
                topic,
                value=json.dumps(event).encode("utf-8"),
                callback=_on_delivery,
            )
            self._producer.flush()  # blocks until ACK or delivery.timeout.ms
        except Exception as exc:
            kafka_produced_total.labels(status="failure").inc()
            logger.error("Kafka produce error: %s", type(exc).__name__)
            return False

        return delivery_result["success"]
