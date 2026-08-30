"""Turn the aggregated subagent signals into a root cause, a proposed fix and a risk score."""
from __future__ import annotations

import math
import re

_UNIT_MIB = {
    "Ki": 1 / 1024, "Mi": 1.0, "Gi": 1024.0,
    "K": 1e3 / 1048576, "M": 1e6 / 1048576, "G": 1e9 / 1048576,
}


def _to_mib(value: str) -> float | None:
    """Parse a Kubernetes quantity like '480Mi' / '1Gi' / '512' into MiB, or None if unparseable."""
    if not (match := re.match(r"^\s*([0-9.]+)\s*(Ki|Mi|Gi|K|M|G)?\s*$", value or "")):
        return None
    return float(match.group(1)) * _UNIT_MIB[match.group(2) or "Mi"]


def _recommend_mib(peak_mib: float) -> int:
    """Recommend a memory limit ~1.6x the observed peak, rounded up to 128 MiB, min 256 MiB."""
    return max(256, int(math.ceil(peak_mib * 1.6 / 128) * 128))


def _memory_patch(container: str, limit_mib: int) -> dict:
    """Strategic-merge patch that raises one container's memory limit/request on its Deployment."""
    return {"spec": {"template": {"spec": {"containers": [{
        "name": container,
        "resources": {"limits": {"memory": f"{limit_mib}Mi"},
                      "requests": {"memory": f"{max(limit_mib // 2, 128)}Mi"}},
    }]}}}}


def synthesize(*, k8s: dict, api: dict, logs: dict, db: dict, meta: dict | None = None) -> dict:
    """Synthesize an RCA dict (summary, root_cause, evidence, proposed_fix, risk_score, confidence)."""
    oom = k8s.get("exit_code") == 137 or bool(logs.get("oom_detected"))
    err_rate = float(api.get("error_rate", 0.0) or 0.0)
    pool_used = int(db.get("connection_pool_used", 0) or 0)
    pool_max = max(int(db.get("connection_pool_max", 1) or 1), 1)
    pool_ratio = pool_used / pool_max
    repl_lag = float(db.get("replication_lag_s", 0.0) or 0.0)

    signals = list(filter(None, [
        (k8s.get("exit_code") == 137) and "OOMKilled — container exceeded its memory limit (exit 137)",
        logs.get("oom_detected") and f"OOM confirmed in container logs: {str(logs.get('last_error', ''))[:120]}",
        err_rate > 0.05 and f"Elevated API error rate at {err_rate * 100:.1f}%",
        pool_ratio > 0.8 and f"DB connection pool near exhaustion ({pool_used}/{pool_max})",
        repl_lag > 10 and f"DB replication lag {repl_lag:.1f}s",
    ]))

    peak_mib = _to_mib(str(k8s.get("memory_usage", ""))) or (512.0 if oom else None)
    container = str(k8s.get("container") or "app")

    if oom and peak_mib:
        limit = _recommend_mib(peak_mib)
        summary = f"Increase {container} memory limit to {limit}Mi (observed peak ~{int(peak_mib)}Mi)"
        fix_plan = {"kind": "memory_limit", "verb": "patch", "resource": "deployment",
                    "patch": _memory_patch(container, limit), "summary": summary}
    elif pool_ratio > 0.8:
        summary = "Increase DB connection pool max (or add PgBouncer) and set a statement timeout"
        fix_plan = {"kind": "pool_and_timeout", "verb": None, "resource": None,
                    "patch": None, "summary": summary}
    elif err_rate > 0.05:
        summary = "Roll back the most recent deployment (kubectl rollout undo)"
        fix_plan = {"kind": "rollback", "verb": "rollout", "resource": "deployment",
                    "args": ["undo"], "summary": summary}
    else:
        summary = "Root cause not conclusive from automated signals — escalate for manual review"
        fix_plan = {"kind": "manual", "verb": None, "resource": None, "patch": None, "summary": summary}

    risk_score = 2 if oom else 4 if pool_ratio > 0.8 else 6 if err_rate > 0.05 else 8
    incomplete = bool(meta and meta.get("degraded"))
    confidence = "HIGH" if len(signals) >= 2 else "MEDIUM" if signals else "LOW"

    return {
        "summary": "; ".join(signals) or "Root cause unclear — escalating for manual review",
        "root_cause": signals[0] if signals else "Unknown",
        "evidence": signals,
        "proposed_fix": summary,
        "fix_plan": fix_plan,
        "risk_score": min(risk_score + (1 if incomplete else 0), 10),
        "confidence": confidence,
        "incomplete_investigation": incomplete,
    }
