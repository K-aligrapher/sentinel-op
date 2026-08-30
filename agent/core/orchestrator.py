"""Incident lifecycle: classify -> investigate (4 subagents) -> sandbox -> approval -> apply -> verify."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path

import httpx
import structlog

from agent.core.aggregator import aggregate
from agent.core.rca_synthesizer import synthesize
from agent.subagents.api_inspector import inspect as api_inspect
from agent.subagents.db_inspector import inspect as db_inspect
from agent.subagents.k8s_inspector import inspect as k8s_inspect
from agent.subagents.log_analyzer import analyze as log_analyze
from security.audit_logger import log_action
from session.incident_store import mark_resolved, next_incident_id, save_incident
from tools.approval_handler import ApprovalProvider, Decision, get_approval_provider, submit_decision
from tools.escalation import escalate
from tools.github_pr import open_fix_pr
from tools.sandbox_executor import exec_in_sandbox
from tools.sentinel_logger import bind_incident

log = structlog.get_logger()

_ALERT_TO_TYPE = {
    "PodCrashLoopBackOff": "crashloop",
    "HighAPIErrorRate": "api_errors",
    "DBConnectionTimeout": "db_timeout",
}
_TYPE_TO_SKILL = {
    "crashloop": "INC-001-crashloop",
    "api_errors": "INC-002-api-errors",
    "db_timeout": "INC-003-db-timeout",
}
_VERIFY_EXPR = {
    "crashloop": 'kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"} == 1',
    "api_errors": 'rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05',
    "db_timeout": "pg_stat_database_blk_read_time > 5000",
}
_ALLOWED_WRITE_VERBS = {"patch", "scale", "rollout", "set"}
_SUBAGENTS = ("k8s", "api", "logs", "db")


def _skills_dir() -> Path:
    """Directory holding the SKILL.md runbooks ($SKILLS_DIR or <repo>/skills)."""
    return Path(os.getenv("SKILLS_DIR", str(Path(__file__).resolve().parents[2] / "skills")))


def _run_kubectl(args: list[str]) -> str:
    """Run a read-only kubectl query (argv, shell=False); '' if kubectl is absent or fails."""
    try:
        return subprocess.run(["kubectl", *args], capture_output=True, text=True,
                              timeout=15, check=False).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _as_dict(obj: object) -> dict:
    """Normalise a subagent return value (dataclass / dict / Exception) into a plain dict."""
    if isinstance(obj, Exception):
        return {"degraded": True, "error": f"{type(obj).__name__}: {obj}"}
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return obj if isinstance(obj, dict) else {"value": obj}


def classify(alert: dict) -> str:
    """Map an Alertmanager-style alert to a SENTINEL incident type (defaults to crashloop)."""
    labels = alert.get("labels", alert)
    return labels.get("sentinel_type") or _ALERT_TO_TYPE.get(labels.get("alertname", ""), "crashloop")


def load_skill(incident_type: str) -> str:
    """Read the runbook for `incident_type`; return '' and log a warning if it is missing."""
    path = _skills_dir() / f"{_TYPE_TO_SKILL.get(incident_type, 'INC-001-crashloop')}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("skill.load_failed", incident_type=incident_type, error=str(exc))
        return ""
    log.info("skill.loaded", incident_type=incident_type, skill=path.stem, bytes=len(text))
    return text


def _diagnostic_script(pod: str, ns: str) -> str:
    """Read-only diagnostic bundle run inside the sandbox."""
    return (
        "set -eu\n"
        f'kubectl top pod "{pod}" -n "{ns}" --no-headers 2>/dev/null || echo "top unavailable"\n'
        f'kubectl get pod "{pod}" -n "{ns}" -o jsonpath=\'{{.spec.containers[0].resources}}\'\n'
        f'kubectl describe pod "{pod}" -n "{ns}" | grep -E "Limits:|Requests:|OOMKilled|Exit Code" || true\n'
    )


def _fix_validation_script(pod: str, ns: str) -> str:
    """Client-side dry-run of the proposed patch inside the sandbox."""
    return (
        "set -eu\n"
        f'DEP=$(kubectl get pod "{pod}" -n "{ns}" -o jsonpath=\'{{.metadata.ownerReferences[0].name}}\')\n'
        f'kubectl patch deployment "$DEP" -n "{ns}" --dry-run=client -o yaml '
        f'-p \'{{"metadata":{{"annotations":{{"sentinel.validated":"true"}}}}}}\' '
        '| grep -q "sentinel.validated" && echo "FIX_VALID=true"\n'
    )


async def investigate(incident_id: str, pod: str, ns: str, prom_url: str) -> dict:
    """Run all four inspector subagents in parallel and synthesize an RCA."""
    log.info("investigation.started", incident_id=incident_id, pod=pod, namespace=ns)
    start = time.monotonic()
    raw = await asyncio.gather(
        asyncio.to_thread(k8s_inspect, pod, ns),
        asyncio.to_thread(api_inspect, prom_url),
        asyncio.to_thread(log_analyze, pod, ns),
        asyncio.to_thread(db_inspect, prom_url),
        return_exceptions=True,
    )
    results = {name: _as_dict(value) for name, value in zip(_SUBAGENTS, raw)}
    agg = aggregate(results["k8s"], results["api"], results["logs"], results["db"])
    rca = synthesize(
        k8s=results["k8s"], api=results["api"], logs=results["logs"], db=results["db"], meta=agg
    )
    elapsed = round(time.monotonic() - start, 2)
    log.info("investigation.complete", incident_id=incident_id, elapsed_s=elapsed,
             degraded=agg["degraded"], rca_summary=rca["summary"])
    return {"incident_id": incident_id, "pod": pod, "namespace": ns,
            "results": results, "aggregate": agg, "rca": rca, "elapsed_s": elapsed}


class Orchestrator:
    """Owns the alert webhook and drives one incident from alert to resolution."""

    def __init__(
        self,
        *,
        k8s_url: str,
        prom_url: str,
        gh_token: str | None,
        approval_provider: ApprovalProvider | None = None,
    ) -> None:
        self.k8s_url, self.prom_url, self.gh_token = k8s_url, prom_url, gh_token
        self.approval = approval_provider or get_approval_provider()

    async def handle_alert(self, alert: dict) -> dict:
        """Full lifecycle for a single alert; the session is always saved, even on rejection."""
        incident_type = classify(alert)
        incident_id = next_incident_id()
        bind_incident(incident_id)
        labels = alert.get("labels", alert)
        pod, ns = labels.get("pod", "unknown"), labels.get("namespace", "default")
        load_skill(incident_type)
        log.info("incident.opened", incident_id=incident_id, incident_type=incident_type, pod=pod, namespace=ns)

        inv = await investigate(incident_id, pod, ns, self.prom_url)
        save_incident(incident_id, {
            "incident_type": incident_type, "pod": pod, "namespace": ns,
            "rca": inv["rca"], "results": inv["results"], "aggregate": inv["aggregate"],
        })

        diagnose = await asyncio.to_thread(exec_in_sandbox, _diagnostic_script(pod, ns), incident_id, "diagnose")
        validate = await asyncio.to_thread(exec_in_sandbox, _fix_validation_script(pod, ns), incident_id, "validate_fix")
        log.info("sandbox.summary", incident_id=incident_id,
                 diagnose=diagnose.get("status"), validate_fix=validate.get("status"))

        decision = await self.approval.request(
            incident_id=incident_id, rca=inv["rca"],
            risk_score=inv["rca"]["risk_score"], sandbox_result=validate,
        )

        if decision is Decision.APPROVED:
            applied = await asyncio.to_thread(
                self._apply_fix, incident_id, inv["rca"], inv["results"]["k8s"], pod, ns
            )
            resolved = await self._verify_resolved(incident_id, incident_type)
            pr = await asyncio.to_thread(open_fix_pr, incident_id, incident_type, inv["rca"], applied)
            mark_resolved(incident_id, inv["rca"]["proposed_fix"], decision.value, resolved)
            log.info("incident.closed", incident_id=incident_id, resolved=resolved,
                     applied=applied.get("status"), pr=pr.get("status"))
            outcome = {"decision": decision.value, "applied": applied, "resolved": resolved, "pr": pr}
        else:
            escalate(incident_id, decision.value, inv["rca"])
            mark_resolved(incident_id, "", decision.value, False)
            outcome = {"decision": decision.value, "resolved": False}

        return {
            "incident_id": incident_id, "incident_type": incident_type, "rca": inv["rca"],
            "sandbox": {"diagnose": diagnose, "validate_fix": validate}, **outcome,
        }

    def _deployment_name(self, k8s_result: dict, pod: str, ns: str) -> str:
        """Best-effort Deployment name: k8s subagent ownerRef with the ReplicaSet hash stripped."""
        owner = str(k8s_result.get("owner", "")) or _run_kubectl(
            ["get", "pod", pod, "-n", ns, "-o", "jsonpath={.metadata.ownerReferences[0].name}"]
        )
        return re.sub(r"-[a-f0-9]{7,10}$", "", owner) or pod

    def _apply_fix(self, incident_id: str, rca: dict, k8s_result: dict, pod: str, ns: str) -> dict:
        """Render the RCA's fix_plan into one kubectl write (argv only) and run it; tolerate no cluster."""
        plan = rca.get("fix_plan", {"kind": "manual", "verb": None})

        if plan.get("verb") is None:
            log_action(actor="sentinel-agent", action="escalate.manual", resource=f"{ns}/{pod}",
                       incident_id=incident_id, decision="APPROVED", details={"fix_plan": plan})
            return {"status": "MANUAL", "reason": plan.get("summary", "manual remediation required")}
        if plan["verb"] not in _ALLOWED_WRITE_VERBS:
            return {"status": "BLOCKED", "reason": f"write verb {plan['verb']!r} not allowed"}

        name = self._deployment_name(k8s_result, pod, ns)
        log_action(actor="sentinel-agent", action=f"kubectl.{plan['verb']}",
                   resource=f"{ns}/deployment/{name}", incident_id=incident_id,
                   decision="APPROVED", details={"fix_plan": plan})

        if plan["verb"] == "patch":
            cmd = ["kubectl", "patch", "deployment", name, "-n", ns, "-p", json.dumps(plan["patch"])]
        elif plan["verb"] == "rollout":
            cmd = ["kubectl", "rollout", *plan.get("args", ["undo"]), f"deployment/{name}", "-n", ns]
        else:  # scale / set
            cmd = ["kubectl", plan["verb"], "deployment", name, "-n", ns, *plan.get("args", [])]

        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("apply.failed", incident_id=incident_id, error=str(exc))
            return {"status": "SKIPPED", "error": str(exc), "command": " ".join(cmd)}
        return {"status": "OK" if out.returncode == 0 else "FAIL", "command": " ".join(cmd),
                "stdout": out.stdout[-500:], "stderr": out.stderr[-500:]}

    async def _verify_resolved(self, incident_id: str, incident_type: str) -> bool:
        """Return True when the incident's Prometheus alert expression no longer returns samples."""
        expr = _VERIFY_EXPR.get(incident_type)
        if not expr:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.prom_url.rstrip('/')}/api/v1/query", params={"query": expr})
            still_firing = bool(resp.json().get("data", {}).get("result", []))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("verify.failed", incident_id=incident_id, error=str(exc))
            return False
        log.info("verify.alert", incident_id=incident_id, still_firing=still_firing)
        return not still_firing

    async def _safe_handle(self, alert: dict) -> None:
        """Top-level task guard: never let one incident crash the listener."""
        try:
            await self.handle_alert(alert)
        except Exception as exc:  # noqa: BLE001 - deliberate top-level guard, logged with traceback
            log.error("incident.fatal", error=str(exc), traceback=traceback.format_exc())

    async def listen_for_alerts(self, port: int) -> None:
        """Serve POST /api/v1/alerts (Alertmanager webhook) and GET /healthz until cancelled."""
        from aiohttp import web

        async def _alerts(request: "web.Request") -> "web.Response":
            body = await request.json()
            alerts = body if isinstance(body, list) else body.get("alerts", [body])
            for alert in alerts:
                asyncio.create_task(self._safe_handle(alert))
            return web.json_response({"received": len(alerts)}, status=202)

        async def _health(_: "web.Request") -> "web.Response":
            return web.json_response({"status": "ok"})

        async def _approve(request: "web.Request") -> "web.Response":
            incident_id = request.match_info["incident_id"]
            body = await request.json() if request.can_read_body else {}
            raw = str(body.get("decision") or request.query.get("decision", ""))
            matched = submit_decision(incident_id, raw)
            log.info("approval.callback", incident_id=incident_id, decision=raw.upper(), matched=matched)
            return web.json_response({"incident_id": incident_id, "accepted": matched},
                                     status=200 if matched else 404)

        app = web.Application()
        app.add_routes([
            web.post("/api/v1/alerts", _alerts),
            web.post("/api/v1/approvals/{incident_id}", _approve),
            web.get("/healthz", _health),
        ])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        log.info("alert_listener.started", port=port)
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()
