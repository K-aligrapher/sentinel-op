"""K8s Inspector subagent — pod state, restart count, exit code and warning events via kubectl."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field


def _kubectl_timeout_s() -> int:
    """kubectl call timeout in seconds from $KUBECTL_TIMEOUT_SECONDS (default 15)."""
    return int(os.getenv("KUBECTL_TIMEOUT_SECONDS", "15"))


@dataclass
class K8sResult:
    """Structured result of inspecting a single pod."""

    pod: str
    namespace: str
    status: str
    restart_count: int
    exit_code: int | None
    memory_usage: str
    events: list[str] = field(default_factory=list)
    degraded: bool = False
    error: str | None = None


def _run(args: list[str]) -> str:
    """Run a read-only kubectl command (argv only, shell=False); return stdout or '' on failure."""
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=_kubectl_timeout_s(), check=False
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def inspect(pod: str, ns: str = "default") -> K8sResult:
    """Describe `pod` in `ns` and pull exit code, restart count, memory use and warning events."""
    if not shutil.which("kubectl"):
        return K8sResult(pod, ns, "unknown", 0, None, "unknown", degraded=True, error="kubectl not found")

    describe = _run(["kubectl", "describe", "pod", pod, "-n", ns])
    if not describe:
        return K8sResult(pod, ns, "unknown", 0, None, "unknown", degraded=True,
                         error="kubectl describe returned no output")
    top = _run(["kubectl", "top", "pod", pod, "-n", ns, "--no-headers"])

    lines = describe.splitlines()
    exit_code = next(
        (int(part) for line in lines if "Exit Code:" in line
         if (part := line.split("Exit Code:")[-1].strip()).lstrip("-").isdigit()),
        None,
    )
    restart_count = next(
        (int(line.split()[-1]) for line in lines
         if "Restart Count:" in line and line.split()[-1].isdigit()),
        0,
    )
    status = next(
        (line.split()[-1] for line in lines if line.strip().startswith("Status:")), "unknown"
    )
    memory_usage = top.split()[2] if len(top.split()) >= 3 else "unknown"
    events = [line.strip() for line in lines if "Warning" in line or "Error" in line]

    return K8sResult(pod, ns, status, restart_count, exit_code, memory_usage, events)
