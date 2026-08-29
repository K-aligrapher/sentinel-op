"""Log Analyzer subagent — scan the previous container's logs for known failure signatures."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

_ERROR_RE = re.compile(
    r"(ERROR|FATAL|PANIC|OOM|killed|segfault|exception|traceback|connection refused)",
    re.IGNORECASE,
)


def _kubectl_timeout_s() -> int:
    """kubectl call timeout in seconds from $KUBECTL_TIMEOUT_SECONDS (default 15)."""
    return int(os.getenv("KUBECTL_TIMEOUT_SECONDS", "15"))


@dataclass
class LogResult:
    """De-duplicated error signatures found in a pod's previous-container logs."""

    pod: str
    error_patterns: list[str] = field(default_factory=list)
    last_error: str = ""
    oom_detected: bool = False
    degraded: bool = False
    error: str | None = None


def analyze(pod: str, ns: str = "default", tail: int = 100) -> LogResult:
    """Read the last `tail` lines of `pod`'s previous container and classify error lines."""
    if not shutil.which("kubectl"):
        return LogResult(pod, degraded=True, error="kubectl not found")
    try:
        raw = subprocess.run(
            ["kubectl", "logs", pod, "-n", ns, "--previous", f"--tail={tail}"],
            capture_output=True, text=True, timeout=_kubectl_timeout_s(), check=False,
        ).stdout.splitlines()
    except (subprocess.SubprocessError, OSError) as exc:
        return LogResult(pod, degraded=True, error=str(exc))

    errors = [line for line in raw if _ERROR_RE.search(line)]
    return LogResult(
        pod=pod,
        error_patterns=sorted({re.sub(r"\d+", "N", e)[:80] for e in errors}),
        last_error=errors[-1][:200] if errors else "",
        oom_detected=any("oom" in e.lower() or "killed" in e.lower() for e in errors),
    )
