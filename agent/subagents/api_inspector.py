"""API Inspector subagent — error rate, throughput and p99 latency from Prometheus."""
from __future__ import annotations

from dataclasses import dataclass, field

from agent.subagents._prom import prom_base, query, scalar

_ERR_RATE_EXPR = 'rate(http_requests_total{status=~"5.."}[5m])'
_TOTAL_RATE_EXPR = "rate(http_requests_total[5m])"
_P99_EXPR = "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))"


@dataclass
class APIResult:
    """Structured API health snapshot."""

    error_rate: float
    p99_latency_ms: float
    rps: float
    top_errors: list[str] = field(default_factory=list)
    degraded: bool = False
    error: str | None = None


def inspect(prom_url: str | None = None) -> APIResult:
    """Compute 5xx error rate, requests-per-second and p99 latency from HTTP metrics."""
    base = prom_base(prom_url)
    total = query(base, _TOTAL_RATE_EXPR)
    if not total:
        return APIResult(0.0, 0.0, 0.0, [], degraded=True, error="no http_requests_total samples")
    tot = scalar(total, default=0.0)
    err = scalar(query(base, _ERR_RATE_EXPR))
    p99 = scalar(query(base, _P99_EXPR))
    return APIResult(
        error_rate=round(err / tot, 4) if tot else 0.0,
        p99_latency_ms=round(p99 * 1000, 1),
        rps=round(tot, 2),
        top_errors=[],
    )
