# 🛡️ SENTINEL — Autonomous Production Incident Commander

SENTINEL responds to production incidents without human toil. When Prometheus fires an
alert, SENTINEL spawns **four parallel subagents** to investigate Kubernetes, APIs, logs
and the database simultaneously, runs diagnostics in an **isolated Daytona sandbox**,
synthesizes a root-cause analysis, proposes a **sandbox-validated fix**, and only then
requests **human approval** before touching production. Every incident is **persisted**
for post-mortems and pattern matching.

Built on **TrueForge** (agent harness) with **MCP** servers for real tooling. Every PR is
reviewed by **Qodo**. Code follows the **Ponytail** standard — one expression when one
expression fits.

---

## Repository layout

```
sentinel/
├── agent/
│   ├── main.py                 # entry point — validates env, starts alert listener
│   ├── core/
│   │   ├── orchestrator.py     # investigate() + Orchestrator (webhook + lifecycle)
│   │   ├── aggregator.py       # merge 4 subagent results, flag degraded ones
│   │   └── rca_synthesizer.py  # signals → root cause + proposed fix + risk score
│   ├── subagents/
│   │   ├── k8s_inspector.py    # kubectl describe / top / events
│   │   ├── api_inspector.py    # Prometheus error rate / p99 / rps
│   │   ├── log_analyzer.py     # previous-container log signature scan
│   │   ├── db_inspector.py     # connection pool / slow queries / replication lag
│   │   └── _prom.py            # shared PromQL helpers
│   └── utils/{retry.py,circuit_breaker.py}
├── tools/
│   ├── sandbox_executor.py     # Daytona: create → exec → ALWAYS destroy
│   ├── approval_handler.py     # file / auto approval providers + timeout → escalate
│   ├── escalation.py           # Slack notify + ERROR log
│   └── sentinel_logger.py      # structlog JSON + secret masking
├── session/
│   ├── incident_store.py       # SQLite (WAL) incident history + next_incident_id()
│   ├── pattern_matcher.py      # similar past incidents (returns [] never None)
│   └── history_reader.py       # human-readable renderings
├── security/{secrets.py,input_sanitizer.py,audit_logger.py}
├── skills/INC-00{1,2,3}-*.md   # TrueForge runbooks
├── config/                     # agent.yaml, alert-rules.yaml, mcp-connectors.yaml
├── mcp/                        # per-server MCP config / env
├── ui/                         # TrueForge dashboard + generative-UI templates
├── deploy/                     # docker-compose, k8s RBAC, Helm chart
├── scripts/                    # trigger_alert.py, verify_infra.py, verify_mcp.py, diagnostics/
├── tests/{unit,integration,e2e}/
└── docs/                       # demo script, blog post, API, PR checklist
```

---

## Quick start (local)

```bash
cd sentinel
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # fill GROQ / GITHUB / DAYTONA keys

# infra (see docs/demo-script.md for the full sequence)
minikube start --memory=4096 --cpus=4
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
kubectl apply -f /tmp/k8s-scenarios/scenarios/crashloopbackoff/issue.yaml

# run the agent
python -m agent.main                                   # listens on :9093

# in another shell — fire a mock alert
python scripts/trigger_alert.py crashloop
```

Approve a proposed fix (default `SENTINEL_APPROVAL_MODE=file`):

```bash
echo APPROVED > logs/approvals/INC-2026-001.decision      # or REJECTED
```

For an unattended demo set `SENTINEL_APPROVAL_MODE=auto` (+ `SENTINEL_AUTO_DECISION`).

---

## One-command stack

```bash
docker compose -f deploy/docker-compose.yml up --build
```

---

## Tests

```bash
pytest tests/unit -v                       # offline, no infra
RUN_INTEGRATION=1 pytest tests/integration  # needs MCP servers / Daytona
pytest -m e2e tests/e2e                     # full lifecycle
```

---

## Incident types covered (v1.0)

| Type | Alert | Runbook |
|------|-------|---------|
| CrashLoopBackOff | `PodCrashLoopBackOff` | `skills/INC-001-crashloop.md` |
| High API error rate | `HighAPIErrorRate` | `skills/INC-002-api-errors.md` |
| DB connection timeout | `DBConnectionTimeout` | `skills/INC-003-db-timeout.md` |

Non-goals for v1.0: cloud K8s, >3 incident types, multi-cluster, real PagerDuty,
auto-merge without approval. See `SENTINEL_PRD.md` §2 and `docs/technical-debt.md`.

---

## Safety guarantees

- All diagnostic / fix code runs in Daytona — **never** on the host or production.
- Every production change requires **human approval**; timeout → **escalation**, never silent apply.
- `security/input_sanitizer.py` blocks dangerous shell patterns and non-read-only `kubectl`.
- Secrets are masked in every log line; `security/audit_logger.py` records every action.
- K8s access via a minimal-permission ServiceAccount (`deploy/k8s-manifests/rbac.yaml`).
