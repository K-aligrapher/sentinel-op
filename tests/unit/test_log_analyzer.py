import subprocess
import types

from agent.subagents import log_analyzer
from agent.subagents.log_analyzer import analyze


def _fake_run(stdout: str):
    return lambda *a, **k: types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)


def test_detects_oom_and_last_error(monkeypatch):
    monkeypatch.setattr(log_analyzer.shutil, "which", lambda _x: "/usr/bin/kubectl")
    monkeypatch.setattr(
        log_analyzer.subprocess, "run",
        _fake_run("starting up\nWARN retrying\nFATAL: OOM allocating 512MiB\nprocess killed\n"),
    )
    result = analyze("api-7f4d", "prod")
    assert result.oom_detected is True
    assert result.last_error == "process killed"          # last matching line
    assert any("OOM" in p for p in result.error_patterns)
    assert result.degraded is False


def test_degraded_when_kubectl_missing(monkeypatch):
    monkeypatch.setattr(log_analyzer.shutil, "which", lambda _x: None)
    result = analyze("api-7f4d", "prod")
    assert result.degraded is True
    assert result.error == "kubectl not found"


def test_degraded_on_subprocess_error(monkeypatch):
    monkeypatch.setattr(log_analyzer.shutil, "which", lambda _x: "/usr/bin/kubectl")

    def _raise(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="kubectl", timeout=15)

    monkeypatch.setattr(log_analyzer.subprocess, "run", _raise)
    assert analyze("api-7f4d", "prod").degraded is True
