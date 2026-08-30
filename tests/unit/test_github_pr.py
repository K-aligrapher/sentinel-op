import functools

import httpx

from tools import github_pr
from tools.github_pr import open_fix_pr

_RCA = {
    "root_cause": "OOMKilled",
    "evidence": ["OOMKilled — exit 137"],
    "proposed_fix": "Increase api memory limit to 768Mi",
    "fix_plan": {"kind": "memory_limit", "verb": "patch"},
    "risk_score": 2,
    "confidence": "HIGH",
}
_APPLIED = {"status": "OK", "command": "kubectl patch deployment api -n prod ..."}


def test_skipped_without_credentials(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert open_fix_pr("INC-2026-001", "crashloop", _RCA, _APPLIED)["status"] == "SKIPPED"


def test_disabled_by_flag(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    monkeypatch.setenv("SENTINEL_OPEN_PR", "0")
    assert open_fix_pr("INC-2026-001", "crashloop", _RCA, _APPLIED)["status"] == "DISABLED"


def test_happy_path_creates_branch_note_and_pr(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    monkeypatch.setenv("SENTINEL_OPEN_PR", "1")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "basesha"}})
        if request.url.path.endswith("/git/refs"):
            return httpx.Response(201, json={})
        if "/contents/" in request.url.path:
            return httpx.Response(201, json={})
        if request.url.path.endswith("/pulls"):
            return httpx.Response(201, json={"html_url": "https://github.com/o/r/pull/42", "number": 42})
        return httpx.Response(500)

    monkeypatch.setattr(
        github_pr.httpx, "Client",
        functools.partial(httpx.Client, transport=httpx.MockTransport(handler)),
    )
    result = open_fix_pr("INC-2026-001", "crashloop", _RCA, _APPLIED)
    assert result == {"status": "OK", "pr_url": "https://github.com/o/r/pull/42",
                      "number": 42, "branch": "fix/inc-2026-001-memory_limit"}
    assert any(s.endswith("/pulls") for s in seen)
    assert any("/contents/incidents/INC-2026-001.md" in s for s in seen)


def test_http_error_is_swallowed(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPO", "o/r")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    monkeypatch.setattr(
        github_pr.httpx, "Client",
        functools.partial(httpx.Client, transport=httpx.MockTransport(handler)),
    )
    assert open_fix_pr("INC-2026-001", "crashloop", _RCA, _APPLIED)["status"] == "ERROR"
