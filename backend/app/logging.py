import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "message": record.getMessage()}
        for key in ("runId", "status", "errorType"):
            if hasattr(record, key):
                payload[key] = str(getattr(record, key))
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("clevis")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
