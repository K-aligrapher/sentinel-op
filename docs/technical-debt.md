# Technical Debt — SENTINEL v1.0

Tracked low-severity items and known limitations. Address post-hackathon.

| # | Item | Impact | v2 fix |
|---|------|--------|--------|
| TD-1 | SQLite has no concurrent writes | One incident at a time | Postgres with row locking (TrueForge hosted mode) |
| TD-2 | Groq free-tier rate limits | Slow under load | Dedicated endpoint or model swap |
| TD-3 | Minikube only | No real cloud K8s | EKS/GKE via kubeconfig federation |
| TD-4 | 3 incident types only | Limited coverage | Add SKILL.md runbooks incrementally |
| TD-5 | Mock PagerDuty webhook | Demo only | PagerDuty Events API v2 |
| TD-6 | `_apply_fix` patches a marker annotation, not the real resource spec | Demo-safe placeholder | Render the concrete patch from the RCA and apply via the write-approved role |
| TD-7 | GitHub PR creation is described in the runbook but not wired into the orchestrator | No PR in offline runs | Add a `github` MCP call after a successful apply |
| TD-8 | Approval provider polls a file every 2s | Fine for demo | Native TrueForge approval callback / websocket |
| TD-9 | Prometheus verify returns `False` when Prometheus is unreachable | Incident marked unresolved | Distinguish "unverified" from "still firing" |
