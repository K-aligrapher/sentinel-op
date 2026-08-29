# SENTINEL: we built an SRE that does the work, not one that gives advice

## The problem: 2 AM, a pager, and 4.5 hours

The industry-average mean time to resolution for a production incident is about four and a
half hours. Most of that is not thinking — it is *toil*. Someone gets paged, opens a
laptop, runs `kubectl describe`, scrolls logs, checks a Grafana board, queries the
database, forms a hypothesis, tries a fix, waits, and repeats. The reasoning takes
minutes; the mechanical work around it takes hours.

We wanted to compress the mechanical part to near zero while keeping a human firmly in
control of anything that touches production.

## What SENTINEL does

When Prometheus fires an alert, SENTINEL:

1. **Identifies the incident type** from the alert metadata and loads the matching
   `SKILL.md` runbook (CrashLoopBackOff, high API error rate, or DB connection timeout).
2. **Spawns four subagents in parallel** — a K8s inspector, an API inspector, a log
   analyzer, and a DB inspector — so the whole system is examined at once instead of
   one probe at a time.
3. **Synthesizes a root-cause analysis** from the combined signals: exit code 137 plus
   "OOM" in the logs means the memory limit is too low; a 5xx spike that lines up with a
   rollout means a bad deploy; a connection pool at 90% means exhaustion.
4. **Runs diagnostics and validates the fix in an isolated Daytona sandbox.** Nothing
   runs on the host or against production during investigation.
5. **Requests human approval** with a concrete diff, a risk score, and the sandbox
   result. Approve and it applies the change via Kubernetes; reject and it proposes an
   alternative; time out and it escalates to on-call. It never applies a change on its
   own.
6. **Verifies the alert cleared, then persists the whole incident** — every subagent
   result, the RCA, the decision, and the outcome — for the post-mortem and for pattern
   matching against future incidents.

The result is not a chatbot that explains what `CrashLoopBackOff` means. It is an
automated SRE that describes the pod, reads the previous container's logs, checks the
metrics, tests a fix in a sandbox, and hands you a one-click decision — in under a
minute.

## How TrueForge made it possible

Four TrueForge primitives map almost exactly onto what an incident responder needs:

- **Parallel subagents.** The four inspectors are independent by construction, so they
  fan out with `asyncio.gather` and the investigation takes as long as the slowest
  probe, not the sum of all four.
- **The approval gate.** Human-in-the-loop is a first-class primitive, not something we
  bolted on. The agent pauses, the UI renders a card, and execution resumes only on an
  explicit decision. Our `ApprovalProvider` abstraction lets the same code run against
  the TrueForge UI, a file drop for local demos, or an auto-approver for tests.
- **Persistent sessions.** Every incident is a session. `session/incident_store.py`
  writes a full JSON blob to SQLite in WAL mode, and `pattern_matcher.py` reads it back
  to answer "have we seen this before?" the next time a similar alert fires.
- **MCP connectors.** Kubernetes, Prometheus, and GitHub are all reached through MCP
  servers, so the agent talks to real tooling with no bespoke glue.

## What broke along the way

- **Daytona timeouts.** Our first sandbox executor leaked workspaces when a script hung.
  The fix was a `finally` block that always issues the delete, plus a `SKIPPED` status
  so the orchestrator can escalate instead of blocking when Daytona is unreachable.
- **Empty PromQL results.** `histogram_quantile` over a metric that does not exist yet
  returns an empty vector, and `float(result[0]...)` throws. Every query now goes
  through a `scalar(vector, default)` helper that degrades to a safe number and marks
  the subagent as degraded rather than crashing the investigation.
- **RBAC mismatch.** The agent's ServiceAccount is read-only by design; the write role
  is a separate `ClusterRole` that is only meant to be bound around an approved apply.
  Getting that split right took a couple of iterations of `kubectl auth can-i`.
- **Prompt injection via logs.** Pod logs are attacker-influenced input. The system
  prompt now explicitly refuses instructions found in tool output, and
  `input_sanitizer.py` blocks dangerous shell patterns before anything reaches the
  sandbox.

## What Qodo caught

Every phase shipped as a PR, and Qodo reviewed each one before merge. The recurring
findings were exactly the ones you would expect from fast hackathon code: a bare
`except:` in the escalation path, a `shell=True` in an early version of the K8s
inspector, an unclosed file handle in the logger factory, and a hardcoded `timeout=10`
that should have been an environment variable. All fixed before merge; the final quality
score cleared our 85/100 bar.

## Results

- Investigation (four subagents, RCA synthesis): **under 15 seconds**.
- Full lifecycle to an approval-ready card: **under a minute**.
- End-to-end demo, alert to resolved and persisted: **under five minutes**.

## What's next

Postgres instead of SQLite for concurrent incidents, real PagerDuty integration, more
`SKILL.md` runbooks, and rendering the concrete resource patch from the RCA instead of
the demo-safe annotation marker. The architecture — fan out, synthesize, sandbox,
approve, verify, persist — stays the same.
