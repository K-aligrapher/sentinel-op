import pytest

from security.secrets import OPTIONAL, validate_env


def test_exits_when_required_missing(monkeypatch):
    monkeypatch.delenv("SENTINEL_SKIP_ENV_CHECK", raising=False)
    for key in ("GROQ_API_KEY", "GITHUB_TOKEN", "DAYTONA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SystemExit):
        validate_env()


def test_returns_optional_defaults_when_all_present(monkeypatch):
    monkeypatch.delenv("SENTINEL_SKIP_ENV_CHECK", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "y")
    monkeypatch.setenv("DAYTONA_API_KEY", "z")
    cfg = validate_env()
    assert set(cfg) == set(OPTIONAL)
    assert cfg["LOG_LEVEL"]


def test_skip_flag_bypasses_check(monkeypatch):
    monkeypatch.setenv("SENTINEL_SKIP_ENV_CHECK", "1")
    for key in ("GROQ_API_KEY", "GITHUB_TOKEN", "DAYTONA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert validate_env()["APPROVAL_TIMEOUT_MINUTES"] == "15"
