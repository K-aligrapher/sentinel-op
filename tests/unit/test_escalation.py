import httpx

from tools import escalation
from tools.escalation import escalate

_RCA = {"summary": "OOMKilled — memory limit exceeded"}


def test_no_webhook_just_logs(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    escalate("INC-2026-001", "rejected", _RCA)  # must not raise


def test_slack_failure_is_swallowed(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/x")

    def _raise(*_a, **_k):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(escalation.httpx, "post", _raise)
    escalate("INC-2026-002", "approval timeout", _RCA)  # must not raise


def test_accepts_plain_string_rca(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    escalate("INC-2026-003", "unknown", "freeform reason")
