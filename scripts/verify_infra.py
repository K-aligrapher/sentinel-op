"""Check that Minikube, Prometheus and a CrashLoopBackOff demo pod are all present."""
from __future__ import annotations

import subprocess

import httpx


def _kubectl_ok() -> bool:
    """True if `kubectl cluster-info` succeeds."""
    try:
        return subprocess.run(
            ["kubectl", "cluster-info"], capture_output=True, timeout=10, check=False
        ).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _prometheus_ready() -> bool:
    """True if Prometheus reports ready on :9090."""
    try:
        return httpx.get("http://localhost:9090/-/ready", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def _crashloop_present() -> bool:
    """True if any pod across namespaces is in CrashLoopBackOff."""
    try:
        out = subprocess.run(
            ["kubectl", "get", "pods", "-A"], capture_output=True, text=True, timeout=10, check=False
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return "CrashLoopBackOff" in out.stdout


_CHECKS = {"minikube": _kubectl_ok, "prometheus": _prometheus_ready, "crashloop_pod": _crashloop_present}


def main() -> int:
    """Run every check, print a ✅/❌ line each, exit 0 only if all pass."""
    results = {name: check() for name, check in _CHECKS.items()}
    for name, ok in results.items():
        print(f"{'✅' if ok else '❌'} {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
