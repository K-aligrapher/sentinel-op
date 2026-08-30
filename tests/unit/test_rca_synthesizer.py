from agent.core.rca_synthesizer import _recommend_mib, _to_mib, synthesize

_EMPTY_API = {"error_rate": 0.0}
_EMPTY_DB = {"connection_pool_used": 0, "connection_pool_max": 50}
_EMPTY_LOGS = {"oom_detected": False, "last_error": ""}


def test_oom_case_produces_low_risk_memory_fix():
    rca = synthesize(
        k8s={"exit_code": 137, "memory_usage": "480Mi", "container": "api"},
        api=_EMPTY_API, logs={"oom_detected": True, "last_error": "FATAL: OOM"}, db=_EMPTY_DB,
    )
    assert rca["risk_score"] == 2
    assert rca["confidence"] == "HIGH"
    assert "memory limit" in rca["proposed_fix"].lower()
    assert "OOMKilled" in rca["root_cause"]

    plan = rca["fix_plan"]
    assert plan["kind"] == "memory_limit" and plan["verb"] == "patch"
    container = plan["patch"]["spec"]["template"]["spec"]["containers"][0]
    assert container["name"] == "api"
    assert container["resources"]["limits"]["memory"] == "768Mi"


def test_api_error_case_plans_a_rollback():
    rca = synthesize(k8s={}, api={"error_rate": 0.18}, logs=_EMPTY_LOGS, db=_EMPTY_DB)
    assert rca["fix_plan"] == {
        "kind": "rollback", "verb": "rollout", "resource": "deployment",
        "args": ["undo"], "summary": rca["proposed_fix"],
    }
    assert rca["risk_score"] == 6


def test_manual_and_pool_plans_have_no_write_verb():
    unclear = synthesize(k8s={}, api=_EMPTY_API, logs=_EMPTY_LOGS, db=_EMPTY_DB)
    pool = synthesize(k8s={}, api=_EMPTY_API, logs=_EMPTY_LOGS,
                      db={"connection_pool_used": 45, "connection_pool_max": 50})
    assert unclear["fix_plan"]["kind"] == "manual" and unclear["fix_plan"]["verb"] is None
    assert pool["fix_plan"]["kind"] == "pool_and_timeout" and pool["fix_plan"]["verb"] is None


def test_unclear_case_escalates_with_high_risk():
    rca = synthesize(k8s={}, api=_EMPTY_API, logs=_EMPTY_LOGS, db=_EMPTY_DB)
    assert rca["risk_score"] == 8
    assert rca["confidence"] == "LOW"
    assert "escalat" in rca["summary"].lower()
    assert rca["evidence"] == []


def test_pool_exhaustion_proposes_pool_fix():
    rca = synthesize(
        k8s={}, api=_EMPTY_API, logs=_EMPTY_LOGS,
        db={"connection_pool_used": 45, "connection_pool_max": 50},
    )
    assert "pool" in rca["proposed_fix"].lower()
    assert rca["risk_score"] == 4


def test_degraded_meta_bumps_risk_by_one():
    base = synthesize(k8s={"exit_code": 137}, api=_EMPTY_API,
                      logs={"oom_detected": True}, db=_EMPTY_DB)
    bumped = synthesize(k8s={"exit_code": 137}, api=_EMPTY_API,
                        logs={"oom_detected": True}, db=_EMPTY_DB, meta={"degraded": ["api"]})
    assert bumped["risk_score"] == base["risk_score"] + 1
    assert bumped["incomplete_investigation"] is True


def test_quantity_parsing():
    assert _to_mib("512Mi") == 512
    assert _to_mib("1Gi") == 1024
    assert _to_mib("garbage") is None
    assert _recommend_mib(480) >= 768 and _recommend_mib(480) % 128 == 0
