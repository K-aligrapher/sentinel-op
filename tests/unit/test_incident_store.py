from session.incident_store import (
    get_recent,
    load_incident,
    mark_resolved,
    next_incident_id,
    save_incident,
)

_RESULTS = {
    "incident_type": "crashloop", "pod": "api-7f4d", "namespace": "prod",
    "rca": {"summary": "OOMKilled — memory limit exceeded", "proposed_fix": "memory.limit 768Mi"},
}


def test_save_and_load_round_trip():
    save_incident("INC-2026-001", _RESULTS)
    row = load_incident("INC-2026-001")
    assert row["incident_type"] == "crashloop"
    assert row["pod"] == "api-7f4d"
    assert "OOMKilled" in row["rca_summary"]
    assert row["resolved"] == 0


def test_load_unknown_returns_none():
    assert load_incident("INC-9999-999") is None


def test_get_recent_zero_returns_empty_list():
    save_incident("INC-2026-001", _RESULTS)
    assert get_recent(0) == []


def test_get_recent_orders_newest_first():
    save_incident("INC-2026-001", _RESULTS)
    save_incident("INC-2026-002", _RESULTS)
    assert [r["id"] for r in get_recent(10)][:2] == ["INC-2026-002", "INC-2026-001"]


def test_next_incident_id_increments():
    first = next_incident_id()
    assert first.endswith("-001")
    save_incident(first, _RESULTS)
    assert next_incident_id().endswith("-002")


def test_mark_resolved_is_preserved_across_resave():
    save_incident("INC-2026-001", _RESULTS)
    mark_resolved("INC-2026-001", "memory.limit 768Mi", "APPROVED", True)
    save_incident("INC-2026-001", _RESULTS)  # re-save must not wipe the decision
    row = load_incident("INC-2026-001")
    assert row["decision"] == "APPROVED"
    assert row["resolved"] == 1
    assert row["fix_applied"] == "memory.limit 768Mi"
