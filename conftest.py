"""Shared test fixtures — every test runs against an isolated temp LOG_DIR and SQLite DB."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Point logs, the incident DB and approval files at a per-test temp directory."""
    logs = tmp_path / "logs"
    (logs / "approvals").mkdir(parents=True)
    monkeypatch.setenv("LOG_DIR", str(logs))
    monkeypatch.setenv("SESSION_DB_PATH", str(logs / "incidents.db"))
    monkeypatch.setenv("SENTINEL_SKIP_ENV_CHECK", "1")
    for var in ("DAYTONA_API_KEY", "SLACK_WEBHOOK_URL", "GITHUB_TOKEN", "GITHUB_REPO"):
        monkeypatch.delenv(var, raising=False)
    yield
