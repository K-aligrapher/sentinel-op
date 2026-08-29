# SENTINEL Demo Script — 5 Minutes

## 0:00 — Setup (30s)
- Show TrueForge running at `localhost:8790`.
- Show Minikube: `kubectl get nodes`.
- Show Prometheus at `localhost:9090` — no alerts firing.

## 0:30 — Trigger the incident (15s)
```bash
kubectl apply -f /tmp/k8s-scenarios/scenarios/crashloopbackoff/issue.yaml
kubectl get pods -w      # watch it crash
```

## 0:45 — SENTINEL activates (30s)
- Alert arrives in TrueForge → "Loading INC-001 runbook".
- 4 subagents appear in a 2×2 grid with spinners.

## 1:15 — Parallel investigation (60s)
- K8s: `OOMKilled exit:137 memory.limit:256Mi`
- Logs: `OOM allocating 512MiB`
- API: `error_rate 18.3%`
- DB: `pool 90% used`

## 2:15 — RCA and sandbox (45s)
- RCA: "Memory limit 256Mi insufficient — OOMKilled".
- Daytona sandbox spins up, diagnostic script runs.
- "Fix validated in sandbox — pod stable".

## 3:00 — Human approval (30s)
- Approval card: fix diff `256Mi → 768Mi`, risk `2/10`, sandbox PASS, 15:00 countdown.
- Click **✅ Approve Fix** (or `echo APPROVED > logs/approvals/<INC-ID>.decision`).

## 3:30 — Fix applied (30s)
- `kubectl patch` runs; pod stabilises.
- Prometheus `PodCrashLoopBackOff` alert clears.

## 4:00 — Session saved (30s)
- Incident appears in Session History as `RESOLVED`.
- GitHub PR `fix/inc-001-memory-oom` created.

## 4:30 — Wrap (30s)
- Show `logs/audit.jsonl` — every action recorded.
- "This is what $300k/hr downtime looks like automated."

---

### Offline dry run (no cluster)
```bash
SENTINEL_APPROVAL_MODE=auto SENTINEL_SKIP_ENV_CHECK=1 python -m agent.main &
python scripts/trigger_alert.py crashloop
tail -f logs/sentinel.jsonl
```
