---
name: INC-003-db-timeout
description: Investigation and remediation runbook for database connection timeouts / pool exhaustion
version: 1.0
incident_type: db_timeout
alert: DBConnectionTimeout
---

# INC-003 — DB Connection Timeout Runbook

## Trigger Condition
`pg_stat_database_blk_read_time > 5000` (or app-side "connection pool timeout") for > 1 minute.

## Step 1 — DB Subagent
Query Prometheus:
- Pool in use: `pg_stat_database_numbackends`
- Pool max: `pg_settings_max_connections`
- Active queries: `pg_stat_activity_count{state="active"}`
- Replication lag: `pg_replication_lag`
Compute utilisation = in_use / max.

## Step 2 — Log Subagent
`kubectl logs deploy/<app> -n <ns> --since=15m`.
Look for: `pool timeout`, `too many clients`, `canceling statement due to statement timeout`,
`connection reset by peer`.

## Step 3 — API Subagent
Correlate with API p99 latency and 5xx rate — a slow DB usually shows up there first.

## Step 4 — K8s Subagent
Check whether the app was recently scaled up (more replicas × per-pod pool size can exceed
`max_connections`), or whether a migration / batch job is holding long transactions.

## Step 5 — Diagnosis Decision Tree
| Observation | Root cause | Fix |
|-------------|-----------|-----|
| in_use / max > 0.8, no slow queries | Pool too small for replica count | Raise pool max or lower per-pod pool; consider PgBouncer |
| Few backends, high `blk_read_time` | Missing index / seq scans | Add index (suggest, do not auto-apply), raise `statement_timeout` |
| One long transaction pinning rows | Stuck migration / batch | Terminate the offending backend, escalate to owner |
| Replication lag high | Replica overloaded | Route reads to primary temporarily, scale replica |

## Step 6 — Sandbox Validation
In Daytona: run `EXPLAIN (ANALYZE, BUFFERS)` for the slow query against a snapshot, and
render the proposed pool / config change as a diff. Never run DDL against production.

## Step 7 — Human Approval
Present: pool utilisation, slowest query, proposed pool size / index / timeout change,
risk score, sandbox result. Wait for approval.

## Step 8 — Apply (only after approval)
- Pool size: patch the app Deployment env / config and `kubectl rollout status`.
- `statement_timeout`: `ALTER ROLE <app> SET statement_timeout = '30s'` (DBA-reviewed).
- Index: open a PR with the `CREATE INDEX CONCURRENTLY` statement — do not apply inline.

## Step 9 — Verify
`DBConnectionTimeout` alert clears; pool utilisation drops below 0.7; API latency recovers.

## Risk Matrix
| Change | Risk Score |
|--------|-----------|
| Raise connection pool max | 4 |
| Set `statement_timeout` | 3 |
| Terminate a stuck backend | 5 |
| Add index (via PR, concurrently) | 4 |
