"""Real Daytona sandbox round-trip. Needs DAYTONA_API_KEY; the BLOCKED case runs offline."""
import os

import pytest

from tools.sandbox_executor import exec_in_sandbox

pytestmark = pytest.mark.integration


def test_sandbox_blocks_unsafe_command():
    result = exec_in_sandbox("rm -rf /", incident_id="TEST-002", label="test")
    assert result["status"] == "BLOCKED"


@pytest.mark.skipif(not os.getenv("DAYTONA_API_KEY"), reason="DAYTONA_API_KEY not set")
def test_sandbox_executes_safe_command():
    result = exec_in_sandbox("echo 'SANDBOX_OK'", incident_id="TEST-001", label="test")
    assert result["status"] == "OK"
    assert "SANDBOX_OK" in result["stdout"]
