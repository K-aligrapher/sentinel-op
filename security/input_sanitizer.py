"""Command safety checks and secret masking used before any sandbox exec or log write."""
from __future__ import annotations

import re

import structlog

log = structlog.get_logger()

_BLOCKED = re.compile(
    r"rm\s+-rf|>>\s*/etc|[;&|]\s*curl|\bwget\s|chmod\s+777|\bsudo\b|/etc/passwd|/etc/shadow|"
    r"base64\s+-d\b[^\n]*\|\s*(ba)?sh|curl\s+\S+[^\n|]*\|\s*(ba)?sh|\bmkfs\b|\bdd\s+if=|:\(\)\s*\{\s*:",
    re.IGNORECASE,
)
_ALLOWED_KUBECTL = re.compile(
    r"^kubectl\s+(get|describe|logs|top|diff|explain|api-resources|version|"
    r"patch\s+[^\n]*--dry-run)\b"
)
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(password|api[_-]?key|secret|token)\s*[=:]\s*\S+"), r"\1=REDACTED"),
    (re.compile(r"Bearer\s+\S+"), "Bearer REDACTED"),
    (re.compile(r"\b[A-Za-z0-9_\-]{30,}\b"), "REDACTED_TOKEN"),
]


def is_safe_command(cmd: str) -> bool:
    """True when cmd has no blocked pattern and any bare `kubectl` call is read-only / dry-run."""
    if _BLOCKED.search(cmd):
        log.error("security.blocked_command", cmd=cmd[:120], reason="blocked_pattern")
        return False
    if cmd.strip().startswith("kubectl") and not _ALLOWED_KUBECTL.match(cmd.strip()):
        log.warning("security.kubectl_not_whitelisted", cmd=cmd[:120])
        return False
    return True


def mask_secrets(text: str) -> str:
    """Redact tokens, bearer headers and key=value secrets from a string before it is logged."""
    if not isinstance(text, str):
        return text
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text
