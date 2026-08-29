"""DB Inspector subagent — connection pool, query and replication metrics from Prometheus."""
from __future__ import annotations

from dataclasses import dataclass

from agent.subagents._prom import prom_base, query, scalar


@dataclass
class DBResult:
    """Structured database health snapshot."""

    connection_pool_used: int
    connection_pool_max: int
    active_queries: int
    slow_queries: int
    replication_lag_s: float
    degraded: bool = False
    error: str | None = None


def inspect(prom_url: str | None = None) -> DBResult:
    """Read pool usage, active/slow query counts and replication lag from Postgres exporter metrics."""
    base = prom_base(prom_url)
    used = query(base, "pg_stat_database_numbackends")
    if not used:
        return DBResult(0, 100, 0, 0, 0.0, degraded=True, error="no pg_stat_database metrics")
    return DBResult(
        connection_pool_used=int(scalar(used)),
        connection_pool_max=int(scalar(query(base, "pg_settings_max_connections"), default=100)),
        active_queries=int(scalar(query(base, 'pg_stat_activity_count{state="active"}'))),
        slow_queries=int(scalar(query(base, "pg_stat_statements_calls"))),
        replication_lag_s=round(scalar(query(base, "pg_replication_lag")), 2),
    )
