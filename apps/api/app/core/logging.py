import json
import logging
from datetime import UTC, datetime

# Metadata that may be attached via `extra=`. Values must be identifiers, counts or
# enumerations: never payloads, headers, prompts, secrets or exception text.
ALLOWED_FIELDS = (
    "request_id",
    "correlation_id",
    "trace_id",
    "status_code",
    "duration_ms",
    "tenant_id",
    "environment_id",
    "job_id",
    "provider",
    "model",
    "alias",
    "purpose",
    "status",
    "latency_ms",
    "fallback",
    "attempt",
    "error_kind",
    "integration_id",
    "integration_key",
    "operation",
    "webhook_event_id",
    "conversation_id",
    "agent",
    "tool",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Allowlisted fields only: never serialize payloads, headers or exception text.
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ALLOWED_FIELDS:
            value = getattr(record, key, None)
            if isinstance(value, (str, int, float, bool)):
                payload[key] = value
            elif value is not None:
                payload[key] = str(value)
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("platform")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
