"""Fire a mock Alertmanager alert at the SENTINEL webhook (used for demos and tests)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import httpx

_ALERT_TYPES: dict[str, dict[str, str]] = {
    "crashloop": {"alertname": "PodCrashLoopBackOff", "severity": "critical",
                  "sentinel_type": "crashloop", "pod": "api-server-7f4d", "namespace": "prod"},
    "apierror": {"alertname": "HighAPIErrorRate", "severity": "critical",
                 "sentinel_type": "api_errors", "service": "api-gateway", "namespace": "prod"},
    "dbtimeout": {"alertname": "DBConnectionTimeout", "severity": "warning",
                  "sentinel_type": "db_timeout", "db": "primary", "namespace": "prod"},
}


def _live_pod(name_prefix: str, namespace: str) -> str:
    """Newest running pod in `namespace` whose name starts with `name_prefix`.

    Lets the crashloop demo target a Deployment's real pod (``<name>-<rs>-<hash>``)
    so the k8s inspector's ``kubectl describe pod`` resolves. Falls back to the
    prefix itself if kubectl is unavailable or matches nothing.
    """
    try:
        out = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "--sort-by=.metadata.creationTimestamp",
             "-o", "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return name_prefix
    matches = [p for p in out.split() if p.startswith(name_prefix)]
    return matches[-1] if matches else name_prefix


def fire(alert_type: str, host: str) -> dict:
    """POST one alert of the given type to `host` and return the HTTP status and body."""
    labels = dict(_ALERT_TYPES[alert_type])
    if alert_type == "crashloop":
        labels["pod"] = _live_pod(labels["pod"], labels["namespace"])
    payload = [{
        "labels": labels,
        "annotations": {"fired_at": datetime.now(timezone.utc).isoformat()},
    }]
    resp = httpx.post(f"{host}/api/v1/alerts", json=payload, timeout=5)
    return {"status": resp.status_code, "fired": alert_type, "body": resp.text[:200]}


def main() -> int:
    """CLI: `trigger_alert.py [crashloop|apierror|dbtimeout] [--host URL]`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alert_type", nargs="?", default="crashloop", choices=sorted(_ALERT_TYPES))
    parser.add_argument("--host", default=f"http://localhost:{os.getenv('ALERT_WEBHOOK_PORT', '9093')}")
    args = parser.parse_args()
    try:
        print(json.dumps(fire(args.alert_type, args.host)))
    except httpx.HTTPError as exc:
        print(f"failed to fire alert: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
