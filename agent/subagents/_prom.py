"""Shared Prometheus query helpers for the API and DB subagents."""
from __future__ import annotations

import os

import httpx


def _timeout_s() -> int:
    """PromQL query timeout in seconds from $PROM_QUERY_TIMEOUT_SECONDS (default 10)."""
    return int(os.getenv("PROM_QUERY_TIMEOUT_SECONDS", "10"))


def prom_base(explicit: str | None = None) -> str:
    """Resolve the Prometheus base URL from an explicit arg or $PROMETHEUS_URL."""
    return (explicit or os.getenv("PROMETHEUS_URL", "http://localhost:9090")).rstrip("/")


def query(base: str, expr: str) -> list[dict]:
    """Run one instant PromQL query, returning the result vector ([] on any error or empty)."""
    try:
        payload = httpx.get(f"{base}/api/v1/query", params={"query": expr}, timeout=_timeout_s()).json()
    except (httpx.HTTPError, ValueError):
        return []
    return payload.get("data", {}).get("result", []) if payload.get("status") == "success" else []


def scalar(vector: list[dict], default: float = 0.0) -> float:
    """Extract the first sample value from a PromQL result vector, or `default` when absent."""
    try:
        return float(vector[0]["value"][1]) if vector else default
    except (KeyError, IndexError, TypeError, ValueError):
        return default
