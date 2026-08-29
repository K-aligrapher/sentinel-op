from tools.sandbox_executor import exec_in_sandbox


def test_blocks_unsafe_command_before_touching_daytona(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_KEY", "should-not-be-used")
    result = exec_in_sandbox("rm -rf /", incident_id="TEST-001", label="test")
    assert result["status"] == "BLOCKED"


def test_skips_when_no_credentials(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    result = exec_in_sandbox("echo SANDBOX_OK", incident_id="TEST-002", label="test")
    assert result["status"] == "SKIPPED"
    assert result["label"] == "test"
