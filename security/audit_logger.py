"""Immutable audit trail — every agent action that touches a resource is appended here."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import structlog

_audit = structlog.get_logger("sentinel.audit")


def _audit_file() -> Path:
    """Resolve logs/audit.jsonl from $LOG_DIR at call time (keeps tests isolatable)."""
    return Path(os.getenv("LOG_DIR", "./logs")) / "audit.jsonl"


def log_action(
    *,
    actor: str,
    action: str,
    resource: str,
    incident_id: str,
    decision: str | None = None,
    details: dict | None = None,
) -> None:
    """Append one audit record (never rotated) and mirror it to the audit logger."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "resource": resource,
        "incident_id": incident_id,
        "decision": decision,
        "details": details or {},
    }
    path = _audit_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    _audit.info("audit", **{k: v for k, v in entry.items() if v is not None})
