from agent.core.aggregator import aggregate

_OK = {"degraded": False}


def test_all_ok_is_complete():
    agg = aggregate(_OK, _OK, _OK, _OK)
    assert agg["complete"] is True
    assert agg["degraded"] == []
    assert agg["subagents"] == {"k8s": "ok", "api": "ok", "logs": "ok", "db": "ok"}


def test_one_degraded_marks_incomplete():
    agg = aggregate(_OK, {"degraded": True, "error": "boom"}, _OK, _OK)
    assert agg["complete"] is False
    assert agg["degraded"] == ["api"]
    assert agg["subagents"]["api"] == "degraded"
