import asyncio

import pytest

from tools import approval_handler
from tools.approval_handler import (
    CallbackApprovalProvider,
    Decision,
    get_approval_provider,
    submit_decision,
)

_RCA = {"proposed_fix": "bump mem", "fix_plan": {"kind": "memory_limit"}}


@pytest.fixture(autouse=True)
def _no_card_post(monkeypatch):
    monkeypatch.setattr(approval_handler.httpx, "post", lambda *a, **k: None)


async def test_callback_resolves_the_pending_request(monkeypatch):
    provider = CallbackApprovalProvider()
    provider.timeout_s = 5
    task = asyncio.create_task(provider.request(
        incident_id="INC-2026-050", rca=_RCA, risk_score=2, sandbox_result={"status": "OK"}))
    await asyncio.sleep(0.05)                       # let the future register
    assert submit_decision("INC-2026-050", "approved") is True
    assert await task is Decision.APPROVED


async def test_decision_arriving_before_the_wait_is_not_lost(monkeypatch):
    submit_decision("INC-2026-060", "APPROVED")          # human clicks before agent asks
    provider = CallbackApprovalProvider()
    provider.timeout_s = 1
    decision = await provider.request(
        incident_id="INC-2026-060", rca=_RCA, risk_score=2, sandbox_result={"status": "OK"})
    assert decision is Decision.APPROVED
    assert "INC-2026-060" not in approval_handler._EARLY


async def test_timeout_escalates(monkeypatch):
    calls = {}
    monkeypatch.setattr(approval_handler, "escalate",
                        lambda iid, reason, rca: calls.update(iid=iid))
    provider = CallbackApprovalProvider()
    provider.timeout_s = 0.05
    decision = await provider.request(
        incident_id="INC-2026-051", rca=_RCA, risk_score=8, sandbox_result={})
    assert decision is Decision.ESCALATED
    assert calls["iid"] == "INC-2026-051"
    assert "INC-2026-051" not in approval_handler._PENDING


def test_get_approval_provider_callback_is_default(monkeypatch):
    monkeypatch.delenv("SENTINEL_APPROVAL_MODE", raising=False)
    assert isinstance(get_approval_provider(), CallbackApprovalProvider)
