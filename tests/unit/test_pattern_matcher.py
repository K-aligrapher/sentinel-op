from session.incident_store import mark_resolved, save_incident
from session.pattern_matcher import find_similar_patterns, suggest_from_history


def _seed(incident_id, summary, resolved=False, fix=""):
    save_incident(incident_id, {
        "incident_type": "crashloop", "pod": "p", "namespace": "prod",
        "rca": {"summary": summary, "proposed_fix": fix},
    })
    if resolved:
        mark_resolved(incident_id, fix, "APPROVED", True)


def test_returns_empty_list_never_none_when_no_history():
    assert find_similar_patterns("memory limit exceeded", "crashloop") == []
    assert suggest_from_history("crashloop") is None


def test_finds_same_type_incident_sharing_a_keyword():
    _seed("INC-2026-001", "OOMKilled because memory limit exceeded on startup")
    matches = find_similar_patterns("pod hit its memory limit again", "crashloop")
    assert [m["id"] for m in matches] == ["INC-2026-001"]


def test_ignores_other_incident_types():
    _seed("INC-2026-001", "memory limit exceeded")
    save_incident("INC-2026-002", {
        "incident_type": "db_timeout", "pod": "p", "namespace": "prod",
        "rca": {"summary": "memory limit exceeded"},
    })
    assert [m["id"] for m in find_similar_patterns("memory limit", "crashloop")] == ["INC-2026-001"]


def test_suggest_from_history_returns_latest_resolved_fix():
    _seed("INC-2026-001", "memory limit", resolved=True, fix="memory.limit 512Mi")
    _seed("INC-2026-002", "memory limit", resolved=True, fix="memory.limit 768Mi")
    assert suggest_from_history("crashloop") == "memory.limit 768Mi"
