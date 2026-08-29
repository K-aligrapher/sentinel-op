"""Human-in-the-loop approval gate. request() blocks until a decision or a timeout escalation."""
from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path

import structlog

from tools.escalation import escalate

log = structlog.get_logger()


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


def get_approval_provider() -> ApprovalProvider:
    """Select a provider from $SENTINEL_APPROVAL_MODE (auto | file); defaults to file."""
    return AutoApproveProvider() if os.getenv("SENTINEL_APPROVAL_MODE", "file").lower() == "auto" \
        else FileApprovalProvider()
