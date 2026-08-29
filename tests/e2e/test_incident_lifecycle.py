"""End-to-end lifecycle with subagents and sandbox stubbed — no cluster required."""
import pytest

from agent.core import orchestrator as orch_mod
from agent.core.orchestrator import Orchestrator
from agent.subagents.api_inspector import APIResult
from agent.subagents.db_inspector import DBResult
from agent.subagents.k8s_inspector import K8sResult
from agent.subagents.log_analyzer import LogResult
from session.history_reader import summarize
from session.incident_store import load_incident
from tools.approval_handler import AutoApproveProvider

pytestmark = pytest.mark.e2e


async def test_crashloop_incident_end_to_end(monkeypatch):
    monkeypatch.setattr(orch_mod, "k8s_inspect", lambda pod, ns: K8sResult(
        pod, ns, "Running", 7, 137, "480Mi", ["Warning OOMKilled exit 137"]))
    monkeypatch.setattr(orch_mod, "api_inspect", lambda prom: APIResult(0.18, 4200.0, 25.0, []))
    monkeypatch.setattr(orch_mod, "log_analyze", lambda pod, ns: LogResult(
        pod, ["FATAL: OOM allocating NMiB"], "FATAL: OOM allocating 512MiB", True))
    monkeypatch.setattr(orch_mod, "db_inspect", lambda prom: DBResult(45, 50, 8, 3, 0.0))
    monkeypatch.setattr(orch_mod, "exec_in_sandbox",
                        lambda script, iid, label: {"status": "OK", "stdout": "FIX_VALID=true", "label": label})
    monkeypatch.setenv("SENTINEL_AUTO_DECISION", "APPROVED")

    orch = Orchestrator(k8s_url="http://k8s", prom_url="http://prom-unreachable:9090",
                        gh_token=None, approval_provider=AutoApproveProvider())
    out = await orch.handle_alert({
        "labels": {"alertname": "PodCrashLoopBackOff", "pod": "api-server-7f4d", "namespace": "prod"}
    })

    assert out["incident_type"] == "crashloop"
    assert out["decision"] == "APPROVED"
    assert out["rca"]["confidence"] == "HIGH"
    assert out["sandbox"]["validate_fix"]["status"] == "OK"

    row = load_incident(out["incident_id"])
    assert row["incident_type"] == "crashloop"
    assert row["decision"] == "APPROVED"
    assert "OOMKilled" in row["rca_summary"]
    assert summarize(out["incident_id"]).startswith(out["incident_id"])
