import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "message": record.getMessage()}
        for key in ("runId", "status", "errorType"):
            if hasattr(record, key):
                payload[key] = str(getattr(record, key))
        return json.dumps(payload)


class TransportPrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # WebSocket protocol DEBUG records may contain auth text and binary frame payloads.
        return not (
            record.levelno <= logging.DEBUG and record.name.startswith(("uvicorn", "websockets"))
        )


def configure_logging(level: str) -> None:
    logger = logging.getLogger("clevis")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    for name in (
        "uvicorn.error",
        "uvicorn",
        "websockets",
        "websockets.server",
        "websockets.client",
    ):
        transport = logging.getLogger(name)
        for target in [transport, *transport.handlers]:
            if not any(isinstance(item, TransportPrivacyFilter) for item in target.filters):
                target.addFilter(TransportPrivacyFilter())
