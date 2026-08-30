"""Human-in-the-loop approval gate. request() blocks until a decision or a timeout escalation."""
from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path

import httpx
import structlog

from tools.escalation import escalate

log = structlog.get_logger()

# Futures awaiting a decision from the callback route, and decisions that arrived early.
_PENDING: dict[str, asyncio.Future] = {}
_EARLY: dict[str, "Decision"] = {}


def _parse(raw: str) -> "Decision":
    """Map free-text ('approved', 'reject', ...) to a Decision, defaulting to REJECTED."""
    value = (raw or "").strip().upper()
    return Decision(value) if value in Decision.__members__ else Decision.REJECTED


def submit_decision(incident_id: str, raw: str) -> bool:
    """Deliver a callback decision. Resolves a waiting request, or stashes it if it arrived first."""
    decision = _parse(raw)
    future = _PENDING.get(incident_id)
    if future is not None and not future.done():
        future.set_result(decision)
        return True
    _EARLY[incident_id] = decision           # decision beat the agent to the wait; keep it
    return True


class Decision(str, Enum):
    """Outcome of an approval request."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class ApprovalProvider:
    """Base provider: emit the request, wait for a decision, escalate on timeout."""

    def __init__(self, timeout_minutes: int | None = None) -> None:
        self.timeout_s = (timeout_minutes or int(os.getenv("APPROVAL_TIMEOUT_MINUTES", "15"))) * 60

    async def request(
        self, *, incident_id: str, rca: dict, risk_score: int, sandbox_result: dict
    ) -> Decision:
        """Log the approval request, await a decision, and escalate + return ESCALATED on timeout."""
        log.info(
            "approval.requested",
            incident_id=incident_id,
            risk_score=risk_score,
            fix=str(rca.get("proposed_fix", ""))[:200],
            sandbox_passed=sandbox_result.get("status") == "OK",
        )
        try:
            decision = await asyncio.wait_for(self._await_decision(incident_id), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            log.warning("approval.timeout", incident_id=incident_id, timeout_s=self.timeout_s)
            escalate(incident_id, "approval timeout", rca)
            return Decision.ESCALATED
        log.info("approval.decided", incident_id=incident_id, decision=decision.value)
        return decision

    async def _await_decision(self, incident_id: str) -> Decision:
        raise NotImplementedError


class AutoApproveProvider(ApprovalProvider):
    """Non-interactive provider for demos and tests; reads $SENTINEL_AUTO_DECISION (default APPROVED)."""

    async def _await_decision(self, incident_id: str) -> Decision:
        raw = os.getenv("SENTINEL_AUTO_DECISION", "APPROVED").upper()
        return Decision(raw) if raw in Decision.__members__ else Decision.APPROVED


class FileApprovalProvider(ApprovalProvider):
    """Polls ``$LOG_DIR/approvals/<incident_id>.decision`` for APPROVED / REJECTED."""

    def __init__(self, timeout_minutes: int | None = None) -> None:
        super().__init__(timeout_minutes)
        self.dir = Path(os.getenv("LOG_DIR", "./logs")) / "approvals"
        self.dir.mkdir(parents=True, exist_ok=True)

    async def _await_decision(self, incident_id: str) -> Decision:
        target = self.dir / f"{incident_id}.decision"
        log.info("approval.awaiting_file", incident_id=incident_id, path=str(target))
        while not target.exists():
            await asyncio.sleep(2)
        raw = target.read_text(encoding="utf-8").strip().upper()
        return Decision(raw) if raw in Decision.__members__ else Decision.REJECTED


class CallbackApprovalProvider(ApprovalProvider):
    """Waits on a Future resolved by ``POST /api/v1/approvals/<id>`` (the TrueForge UI callback).

    Best-effort posts the approval card to TrueForge so the human sees it; the decision
    comes back through the callback route, not by polling.
    """

    def __init__(self, timeout_minutes: int | None = None) -> None:
        super().__init__(timeout_minutes)
        self.trueforge_url = os.getenv("TRUEFORGE_URL", "http://localhost:8790").rstrip("/")

    def _post_card(self, incident_id: str, rca: dict, risk_score: int, sandbox_result: dict) -> None:
        """Push the approval card to TrueForge's generative UI; never raise."""
        card = {"incident_id": incident_id, "risk_score": risk_score,
                "proposed_fix": rca.get("proposed_fix", ""), "fix_plan": rca.get("fix_plan", {}),
                "sandbox_result": sandbox_result.get("status"),
                "callback": f"/api/v1/approvals/{incident_id}"}
        try:
            httpx.post(f"{self.trueforge_url}/api/approvals", json=card, timeout=5)
        except httpx.HTTPError as exc:
            log.warning("approval.card_post_failed", incident_id=incident_id, error=str(exc))

    async def request(
        self, *, incident_id: str, rca: dict, risk_score: int, sandbox_result: dict
    ) -> Decision:
        await asyncio.to_thread(self._post_card, incident_id, rca, risk_score, sandbox_result)
        return await super().request(
            incident_id=incident_id, rca=rca, risk_score=risk_score, sandbox_result=sandbox_result
        )

    async def _await_decision(self, incident_id: str) -> Decision:
        if (early := _EARLY.pop(incident_id, None)) is not None:
            return early
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        _PENDING[incident_id] = future
        log.info("approval.awaiting_callback", incident_id=incident_id,
                 route=f"/api/v1/approvals/{incident_id}")
        try:
            return await future
        finally:
            _PENDING.pop(incident_id, None)


_PROVIDERS = {
    "auto": AutoApproveProvider,
    "file": FileApprovalProvider,
    "callback": CallbackApprovalProvider,
}


def get_approval_provider() -> ApprovalProvider:
    """Select a provider from $SENTINEL_APPROVAL_MODE (callback | file | auto); defaults to callback."""
    return _PROVIDERS.get(os.getenv("SENTINEL_APPROVAL_MODE", "callback").lower(), CallbackApprovalProvider)()
