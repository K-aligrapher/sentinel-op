import os

from tools.sentinel_logger import setup_logging


def test_logs_are_json_and_secrets_masked(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    log = setup_logging()
    log.info("startup", api_key="token=abcd1234abcd1234abcd1234abcd1234", note="hello")
    content = (tmp_path / "sentinel.jsonl").read_text(encoding="utf-8")
    assert '"event": "startup"' in content or '"event":"startup"' in content
    assert "abcd1234abcd1234" not in content
    assert "REDACTED" in content
