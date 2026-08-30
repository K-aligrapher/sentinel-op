import types

import pytest

from agent.core import orchestrator as orch_mod
from agent.core.orchestrator import Orchestrator, classify, investigate
from agent.subagents.api_inspector import APIResult
from agent.subagents.db_inspector import DBResult
from agent.subagents.k8s_inspector import K8sResult
from agent.subagents.log_analyzer import LogResult
from session.incident_store import load_incident
from tools.approval_handler import AutoApproveProvider


def _patch_subagents(monkeypatch, *, degraded_api=False):
    monkeypatch.setattr(orch_mod, "k8s_inspect", lambda pod, ns: K8sResult(
        pod, ns, "Running", 5, 137, "480Mi", ["Warning OOMKilled"]))
    monkeypatch.setattr(orch_mod, "api_inspect", lambda prom: APIResult(
        0.0, 12.0, 30.0, [], degraded=degraded_api, error="x" if degraded_api else None))
    monkeypatch.setattr(orch_mod, "log_analyze", lambda pod, ns: LogResult(
        pod, ["FATAL: OOM"], "FATAL: OOM allocating 512MiB", True))
    monkeypatch.setattr(orch_mod, "db_inspect", lambda prom: DBResult(10, 50, 2, 0, 0.0))
    monkeypatch.setattr(orch_mod, "exec_in_sandbox", lambda script, iid, label: {"status": "SKIPPED", "label": label})


def test_classify_from_alertname():
    assert classify({"labels": {"alertname": "PodCrashLoopBackOff"}}) == "crashloop"
    assert classify({"sentinel_type": "db_timeout"}) == "db_timeout"
    assert classify({"labels": {"alertname": "Unknown"}}) == "crashloop"


async def test_investigate_runs_four_subagents_and_synthesizes(monkeypatch):
    _patch_subagents(monkeypatch)
    result = await investigate("INC-2026-001", "api-7f4d", "prod", "http://prom")
    assert set(result["results"]) == {"k8s", "api", "logs", "db"}
    assert result["aggregate"]["complete"] is True
    assert result["rca"]["risk_score"] == 2
    assert "memory limit" in result["rca"]["proposed_fix"].lower()


async def test_handle_alert_approved_path_persists_decision(monkeypatch):
    _patch_subagents(monkeypatch)
    monkeypatch.setenv("SENTINEL_AUTO_DECISION", "APPROVED")
    orch = Orchestrator(k8s_url="http://k8s", prom_url="http://prom", gh_token=None,
                        approval_provider=AutoApproveProvider())
    out = await orch.handle_alert({"labels": {"alertname": "PodCrashLoopBackOff", "pod": "api-7f4d", "namespace": "prod"}})
    assert out["decision"] == "APPROVED"
    assert out["incident_id"].startswith("INC-")
    row = load_incident(out["incident_id"])
    assert row is not None
    assert row["decision"] == "APPROVED"


def test_apply_fix_renders_memory_patch(monkeypatch):
    captured = {}

    def _fake_run(cmd, **_kw):
        captured["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stdout="patched", stderr="")

    monkeypatch.setattr(orch_mod.subprocess, "run", _fake_run)
    orch = Orchestrator(k8s_url="x", prom_url="y", gh_token=None, approval_provider=AutoApproveProvider())
    rca = {"fix_plan": {"kind": "memory_limit", "verb": "patch", "resource": "deployment",
                        "patch": {"spec": {"x": 1}}, "summary": "bump mem"}}
    result = orch._apply_fix("INC-2026-009", rca, {"owner": "api-server-7f4d8c9b6"}, "api-server-7f4d8c9b6", "prod")
    assert result["status"] == "OK"
    assert captured["cmd"][:5] == ["kubectl", "patch", "deployment", "api-server", "-n"]
    assert '"spec"' in captured["cmd"][-1]


def test_apply_fix_manual_plan_is_not_executed(monkeypatch):
    monkeypatch.setattr(orch_mod.subprocess, "run",
                        lambda *a, **k: pytest.fail("manual plan must not shell out"))
    orch = Orchestrator(k8s_url="x", prom_url="y", gh_token=None, approval_provider=AutoApproveProvider())
    rca = {"fix_plan": {"kind": "manual", "verb": None, "summary": "page a human"}}
    assert orch._apply_fix("INC-2026-010", rca, {}, "p", "prod")["status"] == "MANUAL"


async def test_handle_alert_rejected_still_saves_session(monkeypatch):
    _patch_subagents(monkeypatch)
    monkeypatch.setenv("SENTINEL_AUTO_DECISION", "REJECTED")
    orch = Orchestrator(k8s_url="http://k8s", prom_url="http://prom", gh_token=None,
                        approval_provider=AutoApproveProvider())
    out = await orch.handle_alert({"labels": {"alertname": "PodCrashLoopBackOff", "pod": "p", "namespace": "prod"}})
    assert out["decision"] == "REJECTED"
    assert out["resolved"] is False
    assert load_incident(out["incident_id"])["decision"] == "REJECTED"
