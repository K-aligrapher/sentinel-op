import pytest

from agent.utils.circuit_breaker import CircuitBreaker, State


def _boom():
    raise RuntimeError("dependency down")


def test_opens_after_threshold_then_blocks_calls():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    assert cb.state is State.OPEN
    with pytest.raises(RuntimeError, match="Circuit open"):
        cb.call(lambda: "should not run")


def test_half_open_then_success_closes(monkeypatch):
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=5)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    assert cb.state is State.OPEN
    monkeypatch.setattr("agent.utils.circuit_breaker.time.monotonic", lambda: cb.opened_at + 10)
    assert cb.call(lambda: "recovered") == "recovered"
    assert cb.state is State.CLOSED
    assert cb.failures == 0
