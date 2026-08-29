import pytest

from tools import approval_handler
from tools.approval_handler import (
    AutoApproveProvider,
    Decision,
    FileApprovalProvider,
    get_approval_provider,
)

_RCA = {"proposed_fix": "memory.limit 768Mi", "summary": "OOMKilled"}
_SANDBOX_OK = {"status": "OK"}


async def test_auto_provider_approves_by_default(monkeypatch):
    monkeypatch.setenv("SENTINEL_AUTO_DECISION", "APPROVED")
    provider = AutoApproveProvider()
    decision = await provider.request(
        incident_id="INC-2026-001", rca=_RCA, risk_score=2, sandbox_result=_SANDBOX_OK
    )
    assert decision is Decision.APPROVED


async def test_auto_provider_can_reject(monkeypatch):
    monkeypatch.setenv("SENTINEL_AUTO_DECISION", "REJECTED")
    decision = await AutoApproveProvider().request(
        incident_id="INC-2026-002", rca=_RCA, risk_score=7, sandbox_result={}
    )
    assert decision is Decision.REJECTED


async def test_timeout_triggers_escalation(monkeypatch):
    escalated = {}
    monkeypatch.setattr(
        approval_handler, "escalate",
        lambda incident_id, reason, rca: escalated.update(id=incident_id, reason=reason),
    )
    provider = AutoApproveProvider()
    provider.timeout_s = 0.05

    async def _hang(_incident_id):
        import asyncio

        await asyncio.sleep(10)

    monkeypatch.setattr(provider, "_await_decision", _hang)
    decision = await provider.request(
        incident_id="INC-2026-003", rca=_RCA, risk_score=5, sandbox_result={}
    )
    assert decision is Decision.ESCALATED
    assert escalated["id"] == "INC-2026-003"


async def test_file_provider_reads_written_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    provider = FileApprovalProvider()
    (provider.dir / "INC-2026-004.decision").write_text("APPROVED", encoding="utf-8")
    decision = await provider.request(
        incident_id="INC-2026-004", rca=_RCA, risk_score=2, sandbox_result=_SANDBOX_OK
    )
    assert decision is Decision.APPROVED


def test_get_approval_provider_honours_mode(monkeypatch):
    monkeypatch.setenv("SENTINEL_APPROVAL_MODE", "auto")
    assert isinstance(get_approval_provider(), AutoApproveProvider)
    monkeypatch.setenv("SENTINEL_APPROVAL_MODE", "file")
    assert isinstance(get_approval_provider(), FileApprovalProvider)
