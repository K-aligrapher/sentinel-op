---
name: INC-001-crashloop
description: Investigation and remediation runbook for Kubernetes CrashLoopBackOff incidents
version: 1.0
incident_type: crashloop
alert: PodCrashLoopBackOff
---

# INC-001 — CrashLoopBackOff Runbook

## Trigger Condition
Pod status == `CrashLoopBackOff` for > 1 minute.

## Step 1 — K8s Subagent
Run `kubectl describe pod <pod> -n <ns>` and extract:
- Exit Code (137 = OOMKilled, 1 = app error, 128+signal = crash)
- Restart Count
- Last State → Terminated → Reason

## Step 2 — Log Subagent
Run `kubectl logs <pod> -n <ns> --previous --tail=100`.
Look for: `OOM`, `FATAL`, `PANIC`, `segfault`, missing env var, `connection refused`.

## Step 3 — API Subagent
Query Prometheus: `rate(http_requests_total{status=~"5.."}[5m])`.
If error rate > 5%, document as a secondary symptom.

## Step 4 — Diagnosis Decision Tree
| Observation | Root cause | Fix |
|-------------|-----------|-----|
| Exit 137 + `OOM` in logs | Memory limit too low | Increase `memory.limit` (~1.6× observed peak, min 256Mi) |
| Exit 1 + `env var` in logs | Missing configuration | Check ConfigMap / Secret |
| Exit 1 + `connection refused` | Dependency not ready | Add initContainer / readiness gate |
| Exit 128+N | Signal kill | Increase startup timeout / liveness probe `initialDelaySeconds` |

## Step 5 — Sandbox Validation
Execute `scripts/diagnostics/validate_fix.sh <pod> <ns> <new_memory_limit>` inside Daytona.
Expected output: `FIX_VALID=true`.

## Step 6 — Human Approval
Present: original limit, new limit, restart count, risk score, sandbox result.
Wait for approval before patching. Never auto-apply.

## Step 7 — Apply (only after approval)
```
kubectl patch deployment <name> -n <ns> \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"<c>","resources":{"limits":{"memory":"<new>"}}}]}}}}'
```

## Step 8 — Verify
Confirm the `PodCrashLoopBackOff` alert clears in Prometheus. If it still fires, re-enter
the investigation loop with deeper queries.

## Risk Matrix
| Change | Risk Score |
|--------|-----------|
| Memory increase | 2 |
| Config change | 4 |
| Dependency add | 6 |
| Image change | 7 |
