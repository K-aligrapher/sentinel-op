"""structlog configuration — JSON lines to logs/sentinel.jsonl with secret masking."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import structlog

from security.input_sanitizer import mask_secrets

# Trace/identity fields are safe by construction and must stay readable for log correlation.
_UNMASKED_KEYS = frozenset(
    {"event", "level", "timestamp", "logger", "incident_id", "correlation_id", "workspace_id"}
)


def _mask_processor(_logger: object, _name: str, event_dict: dict) -> dict:
    """structlog processor: redact secrets from string values, except known trace/identity keys."""
    return {
        k: v if k in _UNMASKED_KEYS or not isinstance(v, str) else mask_secrets(v)
        for k, v in event_dict.items()
    }


def setup_logging() -> structlog.BoundLogger:
    """Configure structlog for JSON output at $LOG_LEVEL and return the root logger."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _mask_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(
            file=(log_dir / "sentinel.jsonl").open("a", buffering=1, encoding="utf-8")
        ),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()


def bind_incident(incident_id: str, correlation_id: str | None = None) -> str:
    """Bind incident_id + a correlation_id into contextvars so every later log line carries them."""
    cid = correlation_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(incident_id=incident_id, correlation_id=cid)
    return cid
