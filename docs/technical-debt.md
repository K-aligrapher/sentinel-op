# Technical Debt — SENTINEL v1.0

Tracked low-severity items and known limitations. Address post-hackathon.

| # | Item | Impact | v2 fix |
|---|------|--------|--------|
| TD-1 | SQLite has no concurrent writes | One incident at a time | Postgres with row locking (TrueForge hosted mode) |
| TD-2 | Groq free-tier rate limits | Slow under load | Dedicated endpoint or model swap |
| TD-3 | Minikube only | No real cloud K8s | EKS/GKE via kubeconfig federation |
| TD-4 | 3 incident types only | Limited coverage | Add SKILL.md runbooks incrementally |
| TD-5 | Mock PagerDuty webhook | Demo only | PagerDuty Events API v2 |
| TD-6 | ~~`_apply_fix` patches a marker annotation~~ **Done** — `rca_synthesizer` emits a structured `fix_plan` and `_apply_fix` renders it into a real `kubectl patch` (memory limit) / `rollout undo` (rollback) / `MANUAL` (pool, unclear) | — | Deployment name is a heuristic (ownerRef minus ReplicaSet hash); confirm against `kubectl get deploy` |
| TD-7 | ~~GitHub PR creation not wired in~~ **Done** — `tools/github_pr.py` opens a branch + `incidents/<id>.md` note + PR (GitHub REST) after an approved fix; `SKIPPED` without creds | — | Uses the REST API directly, not the `github` MCP server; swap if MCP tool parity is required |
| TD-8 | ~~Approval provider polls a file~~ **Done** — `CallbackApprovalProvider` waits on a Future resolved by `POST /api/v1/approvals/<id>`; `file` + `auto` remain as fallbacks | — | The approval-card POST targets a guessed `TRUEFORGE_URL/api/approvals` path — confirm against the real TrueForge API |
| TD-9 | Prometheus verify returns `False` when Prometheus is unreachable | Incident marked unresolved | Distinguish "unverified" from "still firing" |
