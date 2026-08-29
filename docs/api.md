# SENTINEL Internal API

## Alert webhook (HTTP)

`POST /api/v1/alerts` on `:$ALERT_WEBHOOK_PORT` (default 9093)

Accepts an Alertmanager-style JSON list, a single alert object, or `{"alerts": [...]}`.
Each alert needs `labels` with either `sentinel_type` (`crashloop` | `api_errors` |
`db_timeout`) or a known `alertname` (`PodCrashLoopBackOff`, `HighAPIErrorRate`,
`DBConnectionTimeout`), plus `pod` and `namespace`.

```json
[{"labels": {"alertname": "PodCrashLoopBackOff", "pod": "api-server-7f4d", "namespace": "prod"}}]
```

Response: `202 {"received": <n>}`. Each alert is handled on its own task.

`GET /healthz` → `200 {"status": "ok"}`.

## Python entry points

| Module | Function | Purpose |
|--------|----------|---------|
| `agent.core.orchestrator` | `investigate(incident_id, pod, ns, prom_url) -> dict` | Run 4 subagents in parallel, return `{results, aggregate, rca, elapsed_s}` |
| `agent.core.orchestrator` | `Orchestrator.handle_alert(alert) -> dict` | Full lifecycle; session always persisted |
| `agent.core.rca_synthesizer` | `synthesize(*, k8s, api, logs, db, meta=None) -> dict` | `summary, root_cause, evidence, proposed_fix, risk_score, confidence` |
| `agent.core.aggregator` | `aggregate(k8s, api, logs, db) -> dict` | `subagents, degraded, complete, results` |
| `tools.sandbox_executor` | `exec_in_sandbox(script, incident_id, label) -> dict` | `status` ∈ `OK / FAIL / BLOCKED / SKIPPED / ERROR`; workspace always destroyed |
| `tools.approval_handler` | `ApprovalProvider.request(*, incident_id, rca, risk_score, sandbox_result) -> Decision` | `APPROVED / REJECTED / ESCALATED`; timeout → escalate |
| `session.incident_store` | `save_incident`, `mark_resolved`, `load_incident`, `get_recent`, `next_incident_id` | SQLite (WAL) persistence; `INC-YYYY-NNN` ids |
| `session.pattern_matcher` | `find_similar_patterns(...) -> list`, `suggest_from_history(type) -> str \| None` | Returns `[]` / `None`, never raises |
| `security.input_sanitizer` | `is_safe_command(cmd) -> bool`, `mask_secrets(text) -> str` | Command allowlist + secret redaction |
| `security.secrets` | `validate_env() -> dict` | Exits if a required secret is missing |

## Subagent result dataclasses

`K8sResult`, `APIResult`, `LogResult`, `DBResult` — each carries `degraded: bool` and
`error: str | None` so the aggregator can flag an incomplete investigation.

## Environment variables

See `SENTINEL_PRD.md` §14-A and `.env.example`. Local-only toggles:
`SENTINEL_SKIP_ENV_CHECK=1`, `SENTINEL_APPROVAL_MODE=auto`, `SENTINEL_AUTO_DECISION`.
