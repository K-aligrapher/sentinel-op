"""Find similar past incidents so SENTINEL can reuse a known-good fix."""
from __future__ import annotations

import structlog

from session.incident_store import get_recent

log = structlog.get_logger()


def find_similar_patterns(rca_summary: str, incident_type: str, n: int = 20) -> list[dict]:
    """Return past incidents of the same type that share a significant word with `rca_summary`."""
    keywords = {word.lower() for word in rca_summary.split() if len(word) > 4}
    similar = [
        h for h in get_recent(n)
        if h["incident_type"] == incident_type
        and any(kw in (h["rca_summary"] or "").lower() for kw in keywords)
    ]
    log.info("pattern.match", found=len(similar), incident_type=incident_type)
    return [{"id": h["id"], "rca": h["rca_summary"], "fix": h["fix_applied"]} for h in similar]


def suggest_from_history(incident_type: str) -> str | None:
    """Return the most recent resolved fix for `incident_type`, or None if there is none."""
    resolved = [
        h for h in get_recent(50)
        if h["incident_type"] == incident_type and h["resolved"] == 1 and h["fix_applied"]
    ]
    return max(resolved, key=lambda h: (h["created_at"], h["id"]))["fix_applied"] if resolved else None
