import json
import logging

SERVICE_NAME = "hackonomics-app"


class RequestIDFilter(logging.Filter):
    """Injects request_id from ContextVar into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        from common.middleware.request_id import current_request_id

        record.request_id = current_request_id.get("")
        return True


class JsonFormatter(logging.Formatter):
    """Emits single-line JSON with service_name, request_id, and level for Loki ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f+00:00"),
            "level": record.levelname.lower(),
            "service_name": SERVICE_NAME,
            "request_id": getattr(record, "request_id", ""),
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)
