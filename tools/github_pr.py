"""Open a pull request documenting an incident and its approved fix, via the GitHub REST API."""
from __future__ import annotations

import base64
import json
import os

import httpx
import structlog

log = structlog.get_logger()


def _repo() -> str:
    """owner/name of the target repo from $GITHUB_REPO."""
    return os.getenv("GITHUB_REPO", "")


def _api() -> str:
    """GitHub API base URL from $GITHUB_API_URL (default api.github.com)."""
    return os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")


def _headers() -> dict:
    """Authorized GitHub API headers using $GITHUB_TOKEN."""
    return {"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN', '')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _branch_name(incident_id: str, rca: dict) -> str:
    """e.g. fix/inc-2026-001-memory_limit."""
    kind = str(rca.get("fix_plan", {}).get("kind", "fix"))
    return f"fix/{incident_id.lower()}-{kind}"


def _pr_body(incident_id: str, incident_type: str, rca: dict, applied: dict) -> str:
    """Markdown PR description: RCA, evidence, fix plan and the live apply result."""
    evidence = "\n".join(f"- {line}" for line in rca.get("evidence", [])) or "- (none)"
    return (
        f"## SENTINEL incident `{incident_id}` — {incident_type}\n\n"
        f"**Root cause:** {rca.get('root_cause', 'Unknown')}\n\n"
        f"**Evidence**\n{evidence}\n\n"
        f"**Proposed fix:** {rca.get('proposed_fix', '')}\n\n"
        f"**Risk score:** {rca.get('risk_score', '?')}/10  ·  "
        f"**Confidence:** {rca.get('confidence', '?')}\n\n"
        f"**fix_plan**\n```json\n{json.dumps(rca.get('fix_plan', {}), indent=2)}\n```\n\n"
        f"**Live apply result:** `{applied.get('status', 'n/a')}`"
        + (f" — `{applied['command']}`" if applied.get("command") else "")
        + "\n\n_Opened automatically after human approval. Review before merge._\n"
    )


def open_fix_pr(incident_id: str, incident_type: str, rca: dict, applied: dict) -> dict:
    """Create a branch + incident note + PR. Returns {status, pr_url?, number?}; never raises."""
    if not os.getenv("SENTINEL_OPEN_PR", "1") == "1":
        return {"status": "DISABLED"}
    if not (os.getenv("GITHUB_TOKEN") and _repo()):
        log.warning("pr.skipped", incident_id=incident_id, reason="no GITHUB_TOKEN / GITHUB_REPO")
        return {"status": "SKIPPED", "reason": "no GitHub credentials"}

    base = os.getenv("GITHUB_DEFAULT_BRANCH", "main")
    branch = _branch_name(incident_id, rca)
    note_path = f"incidents/{incident_id}.md"
    try:
        with httpx.Client(base_url=f"{_api()}/repos/{_repo()}", headers=_headers(), timeout=15) as gh:
            base_sha = gh.get(f"/git/ref/heads/{base}").raise_for_status().json()["object"]["sha"]
            ref = gh.post("/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
            if ref.status_code not in (201, 422):        # 422 => branch already exists
                ref.raise_for_status()
            gh.put(f"/contents/{note_path}", json={
                "message": f"docs(incident): {incident_id} RCA + fix plan",
                "content": base64.b64encode(_pr_body(incident_id, incident_type, rca, applied).encode()).decode(),
                "branch": branch,
            }).raise_for_status()
            pr = gh.post("/pulls", json={
                "title": f"fix({incident_type}): {incident_id} — {rca.get('proposed_fix', '')[:60]}",
                "head": branch, "base": base,
                "body": _pr_body(incident_id, incident_type, rca, applied),
            }).raise_for_status().json()
    except (httpx.HTTPError, KeyError) as exc:
        log.error("pr.failed", incident_id=incident_id, error=str(exc))
        return {"status": "ERROR", "error": str(exc)}

    log.info("pr.opened", incident_id=incident_id, pr_url=pr["html_url"], number=pr["number"])
    return {"status": "OK", "pr_url": pr["html_url"], "number": pr["number"], "branch": branch}
