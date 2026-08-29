"""Ping the K8s, Prometheus and GitHub MCP server health endpoints."""
from __future__ import annotations

import httpx

_ENDPOINTS = {
    "k8s": "http://localhost:8000/healthz",
    "prometheus": "http://localhost:8001/health",
    "github": "http://localhost:8002/healthz",
}


def _reachable(url: str) -> bool:
    """True if the endpoint answers with any non-5xx status."""
    try:
        return httpx.get(url, timeout=5).status_code < 500
    except httpx.HTTPError:
        return False


def main() -> int:
    """Print a ✅/❌ line per MCP server; exit 0 only if all are reachable."""
    results = {name: _reachable(url) for name, url in _ENDPOINTS.items()}
    for name, ok in results.items():
        print(f"{'✅' if ok else '❌'} {name} MCP")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
