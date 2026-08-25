import json
import logging
import re
from datetime import datetime, timezone

from .correlation import get_correlation_id

_SAFE_FIELDS = (
    "event",
    "order_id",
    "session_id",
    "recording_id",
    "shipment_id",
    "notification_id",
    "work_item_id",
    "status",
    "attempt",
    "duration_ms",
    "method",
    "path",
    "status_code",
    "component",
)
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE = re.compile(r"(?<!\w)\+?\d{10,15}(?!\w)")
_SECRET = re.compile(
    r"(?i)\b(password|passwd|secret|token|authorization|api[_-]?key)\s*[=:]\s*[^\s,;]+"
)


def _redact(value: str) -> str:
    value = _EMAIL.sub("[redacted-email]", value)
    value = _PHONE.sub("[redacted-phone]", value)
    return _SECRET.sub(lambda match: f"{match.group(1)}=[redacted]", value)


class JsonFormatter(logging.Formatter):
    """JSON logs with a strict safe-extra allowlist and basic PII redaction."""

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
            "correlation_id": getattr(
                record, "correlation_id", get_correlation_id()
            ),
        }
        for field in _SAFE_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(",", ":"))
