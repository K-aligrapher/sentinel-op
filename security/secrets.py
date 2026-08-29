"""Startup environment-variable validation — the only place secrets are looked up by name."""
from __future__ import annotations

import os
import sys

import structlog

log = structlog.get_logger()

REQUIRED: tuple[str, ...] = ("GROQ_API_KEY", "GITHUB_TOKEN", "DAYTONA_API_KEY")
OPTIONAL: dict[str, str] = {
    "LOG_LEVEL": "INFO",
    "APPROVAL_TIMEOUT_MINUTES": "15",
    "MAX_SANDBOX_EXEC_SECONDS": "120",
}


def validate_env() -> dict[str, str]:
    """Exit the process if any required secret is missing; return resolved optional settings."""
    if os.getenv("SENTINEL_SKIP_ENV_CHECK") == "1":
        log.warning("startup.env_check_skipped")
        return {k: os.getenv(k, v) for k, v in OPTIONAL.items()}
    if missing := [k for k in REQUIRED if not os.getenv(k)]:
        log.error("startup.missing_env", missing=missing)
        sys.exit(f"Missing required env vars: {missing}")
    return {k: os.getenv(k, v) for k, v in OPTIONAL.items()}
