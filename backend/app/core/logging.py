"""Structured (JSON lines) logging with redaction of tokens, passwords and email addresses."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BEARER = re.compile(r"(?i)(bearer\s+)\S+")
_SECRET_KV = re.compile(r"(?i)((?:password|token|secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+")


def redact(text: str) -> str:
    text = _JWT.sub("[jwt]", text)
    text = _BEARER.sub(r"\1[redacted]", text)
    text = _SECRET_KV.sub(r"\1[redacted]", text)
    return _EMAIL.sub(r"\1***@\2", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            entry["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
