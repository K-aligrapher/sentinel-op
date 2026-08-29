---
name: INC-002-api-errors
description: Investigation and remediation runbook for sustained high API 5xx error rates
version: 1.0
incident_type: api_errors
alert: HighAPIErrorRate
---

# INC-002 — High API Error Rate Runbook

## Trigger Condition
`rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05`
sustained for > 2 minutes.

## Step 1 — API Subagent
Query Prometheus:
- Error rate: `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])`
- p99 latency: `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))`
- Throughput: `rate(http_requests_total[5m])`
Record which route / service label carries most of the 5xx volume.

## Step 2 — K8s Subagent
`kubectl get deploy <svc> -n <ns> -o wide` and `kubectl rollout history deploy/<svc> -n <ns>`.
Check for a rollout whose timestamp lines up with the error-rate spike.

## Step 3 — Log Subagent
`kubectl logs deploy/<svc> -n <ns> --since=15m | tail -n 200`.
Look for: upstream `connection refused`, `context deadline exceeded`, `panic`,
`5xx from dependency`, new stack traces since the last deploy.

## Step 4 — DB Subagent
Check `pg_stat_activity` active count and slow queries — a saturated database surfaces
as API 5xx. If the pool is > 80% used, treat this as INC-003 as well.

## Step 5 — Diagnosis Decision Tree
| Observation | Root cause | Fix |
|-------------|-----------|-----|
| 5xx spike starts at a rollout timestamp | Bad deploy | `kubectl rollout undo deploy/<svc>` |
| p99 latency climbing, CPU throttled | Under-provisioned | Scale replicas +1..2 / raise CPU limit |
| Errors only from one dependency | Downstream outage | Enable circuit breaker / fallback, escalate to owner |
| DB pool saturated | Connection exhaustion | Hand to INC-003 |

## Step 6 — Sandbox Validation
Run the rollback or scale change with `--dry-run=client -o yaml` inside Daytona and confirm
the resulting spec. For rollback, diff current vs previous ReplicaSet image.

## Step 7 — Human Approval
Present: error rate, suspected cause, proposed rollback/scale, blast radius, risk score,
sandbox result. Wait for approval.

## Step 8 — Apply (only after approval)
- Rollback: `kubectl rollout undo deployment/<svc> -n <ns>`
- Scale: `kubectl scale deployment/<svc> -n <ns> --replicas=<n>`

## Step 9 — Verify
`HighAPIErrorRate` alert clears and p99 latency returns to baseline within 5 minutes.

## Risk Matrix
| Change | Risk Score |
|--------|-----------|
| Scale replicas up | 3 |
| Rollback deployment | 5 |
| CPU / memory limit change | 4 |
| Circuit-breaker config change | 6 |
