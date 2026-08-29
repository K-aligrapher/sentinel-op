"""Daytona sandbox executor — create a workspace, run a script, ALWAYS destroy it."""
from __future__ import annotations

import base64
import os
import time

import httpx
import structlog

from security.input_sanitizer import is_safe_command

log = structlog.get_logger()


def _api_base() -> str:
    """Daytona API base URL (env-driven so tests can point elsewhere)."""
    return os.getenv("DAYTONA_API_URL", "https://app.daytona.io/api").rstrip("/")


def _max_wait_s() -> int:
    """Per-execution timeout in seconds from $MAX_SANDBOX_EXEC_SECONDS."""
    return int(os.getenv("MAX_SANDBOX_EXEC_SECONDS", "120"))


def exec_in_sandbox(script: str, incident_id: str, label: str) -> dict:
    """Run `script` inside a fresh Daytona workspace and return a structured result.

    The workspace is always destroyed in the ``finally`` block, even on error. When the
    script fails the safety check it is rejected before any workspace is created; when no
    Daytona credentials are configured the call is skipped (logged WARN) so callers can
    still proceed and escalate.
    """
    if not is_safe_command(script):
        log.error("sandbox.blocked", incident_id=incident_id, label=label, reason="unsafe_command")
        return {"status": "BLOCKED", "error": "Command did not pass safety check", "label": label}

    key = os.getenv("DAYTONA_API_KEY")
    if not key:
        log.warning("sandbox.skipped", incident_id=incident_id, label=label, reason="no DAYTONA_API_KEY")
        return {"status": "SKIPPED", "error": "no Daytona credentials", "label": label}

    api, headers = _api_base(), {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    workspace_id: str | None = None
    try:
        with httpx.Client(base_url=api, headers=headers, timeout=_max_wait_s()) as client:
            workspace_id = client.post(
                "/workspaces",
                json={"name": f"sentinel-{incident_id}-{int(time.time())}", "image": "ubuntu:22.04"},
            ).json()["id"]
            log.info("sandbox.created", incident_id=incident_id, workspace_id=workspace_id, label=label)
            encoded = base64.b64encode(script.encode()).decode()
            result = client.post(
                f"/workspaces/{workspace_id}/exec",
                json={"command": f"bash -c 'echo {encoded} | base64 -d | bash'"},
            ).json()
        code = result.get("exit_code")
        log.info("sandbox.complete", incident_id=incident_id, workspace_id=workspace_id,
                 exit_code=code, label=label)
        return {
            "status": "OK" if code == 0 else "FAIL",
            "exit_code": code,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "label": label,
        }
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.error("sandbox.error", incident_id=incident_id, label=label, error=str(exc))
        return {"status": "ERROR", "error": str(exc), "label": label}
    finally:
        if workspace_id:
            try:
                httpx.delete(f"{api}/workspaces/{workspace_id}", headers=headers, timeout=30)
                log.info("sandbox.destroyed", incident_id=incident_id, workspace_id=workspace_id)
            except httpx.HTTPError as exc:
                log.warning("sandbox.destroy_failed", incident_id=incident_id,
                            workspace_id=workspace_id, error=str(exc))
