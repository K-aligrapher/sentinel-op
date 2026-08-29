import pytest

from agent.utils.retry import retry


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("agent.utils.retry.time.sleep", lambda _s: None)


def test_succeeds_after_transient_failures():
    calls = {"n": 0}

    @retry(max_attempts=3, exceptions=(ValueError,))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_reraises_after_exhausting_attempts():
    @retry(max_attempts=2, exceptions=(KeyError,))
    def always_fails():
        raise KeyError("nope")

    with pytest.raises(KeyError):
        always_fails()


def test_does_not_swallow_unlisted_exception():
    @retry(max_attempts=3, exceptions=(ValueError,))
    def wrong_error():
        raise TypeError("unexpected")

    with pytest.raises(TypeError):
        wrong_error()
