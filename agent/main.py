"""SENTINEL entry point — validate the environment, build the orchestrator, listen for alerts."""
from __future__ import annotations

import asyncio
import os

from agent.core.orchestrator import Orchestrator
from security.secrets import validate_env
from tools.sentinel_logger import setup_logging

log = setup_logging()


async def main() -> None:
    """Start the alert webhook listener after checking required secrets are present."""
    cfg = validate_env()
    orch = Orchestrator(
        k8s_url=os.getenv("K8S_MCP_URL", "http://localhost:8000"),
        prom_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
        gh_token=os.getenv("GITHUB_TOKEN"),
    )
    log.info("sentinel.started", version="1.0.0", log_level=cfg.get("LOG_LEVEL"))
    await orch.listen_for_alerts(port=int(os.getenv("ALERT_WEBHOOK_PORT", "9093")))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("sentinel.stopped")
