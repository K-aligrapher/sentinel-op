"""Escalation path — notify a human SRE via Slack and record an ERROR log."""
from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger()


def escalate(incident_id: str, reason: str, rca: dict | str) -> None:
    """Best-effort Slack notification plus a durable ERROR log line; never raises."""
    summary = rca.get("summary", "N/A") if isinstance(rca, dict) else str(rca)
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if webhook:
        text = (
            f"🚨 *SENTINEL Escalation* — `{incident_id}`\n"
            f"Reason: {reason}\nRCA: {summary}\nHuman SRE intervention required."
        )
        try:
            httpx.post(webhook, json={"text": text}, timeout=5)
        except httpx.HTTPError as exc:
            log.warning("escalation.slack_failed", incident_id=incident_id, error=str(exc))
    log.error("escalation.triggered", incident_id=incident_id, reason=reason, rca_summary=summary)
