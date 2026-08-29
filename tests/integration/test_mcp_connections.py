"""Requires the three MCP servers running locally. Enable with RUN_INTEGRATION=1."""
import os

import httpx
import pytest

pytestmark = pytest.mark.integration

_MCP_ENDPOINTS = {
    "k8s": "http://localhost:8000/healthz",
    "prometheus": "http://localhost:8001/health",
    "github": "http://localhost:8002/healthz",
}


@pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to run")
@pytest.mark.parametrize("name,url", list(_MCP_ENDPOINTS.items()))
def test_mcp_health(name, url):
    assert httpx.get(url, timeout=5).status_code < 500, f"{name} MCP unreachable"
