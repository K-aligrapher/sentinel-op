"""Merge the four subagent result dicts and flag which (if any) came back degraded."""
from __future__ import annotations

_NAMES = ("k8s", "api", "logs", "db")


def aggregate(k8s: dict, api: dict, logs: dict, db: dict) -> dict:
    """Return a combined view: per-subagent status, the degraded list, and completeness flag."""
    parts = dict(zip(_NAMES, (k8s, api, logs, db)))
    degraded = [name for name, res in parts.items() if res.get("degraded")]
    return {
        "subagents": {name: ("degraded" if res.get("degraded") else "ok") for name, res in parts.items()},
        "degraded": degraded,
        "complete": not degraded,
        "results": parts,
    }
