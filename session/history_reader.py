"""Human-readable renderings of the incident history for the UI and the demo."""
from __future__ import annotations

from session.incident_store import get_recent, load_incident

_ICON = {0: "⏳", 1: "✅"}


def render_recent(n: int = 10) -> list[str]:
    """One line per recent incident: id, type, resolved icon, truncated RCA summary."""
    return [
        f"{h['id']} [{h['incident_type']}] {_ICON.get(h['resolved'], '⚫')} {(h['rca_summary'] or '')[:80]}"
        for h in get_recent(n)
    ]


def summarize(incident_id: str) -> str | None:
    """Multi-line post-mortem summary for one incident, or None if the id is unknown."""
    inc = load_incident(incident_id)
    return None if inc is None else (
        f"{inc['id']} · {inc['incident_type']} · pod={inc['pod']} ns={inc['namespace']}\n"
        f"RCA:  {inc['rca_summary']}\n"
        f"Fix:  {inc['proposed_fix']}\n"
        f"Decision: {inc['decision'] or 'pending'} · Resolved: {bool(inc['resolved'])}"
    )
