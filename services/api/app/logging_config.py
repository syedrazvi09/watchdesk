import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats each log record as one JSON line.

    Expects the extra structured fields (request_id, tenant, status, etc.)
    to be passed via logging's `extra={...}` argument, which attaches them
    as attributes on the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": "api",
            "message": record.getMessage(),
        }

        # Only include fields that were actually attached to this record,
        # so unrelated log lines (e.g. startup messages) stay clean.
        for field in ("request_id", "tenant", "method", "path", "status", "latency_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)

        return json.dumps(payload)


def configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger("watchdesk.api")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False  # don't also pass records to Uvicorn's own handlers

    return logger
