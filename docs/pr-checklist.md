# Before every PR

- [ ] All new functions have type hints
- [ ] All new functions have docstrings (one line minimum)
- [ ] No bare `except:` clauses — always catch specific exceptions
- [ ] No `shell=True` in subprocess calls — argv list only
- [ ] No hardcoded credentials (`detect-secrets scan` clean)
- [ ] Timeouts come from env vars with a sane default, not literals
- [ ] Files/sockets/DB connections use `with`
- [ ] At least one test per new module
- [ ] `pytest tests/unit` passes locally
- [ ] Sensitive values masked in any new log statements
- [ ] Ponytail pass: loops → comprehensions, if/else → ternary, string builds → `join()`
- [ ] Qodo review read; all 🔴 Critical findings fixed, 🟠 High addressed or ticketed

## Qodo finding triage

| Severity | Action |
|----------|--------|
| 🔴 Critical | Fix before merge — no exceptions |
| 🟠 High | Fix in same PR if < 30 min, else follow-up ticket |
| 🟡 Medium | Fix in next phase's PR |
| 🟢 Low | Log in `docs/technical-debt.md` |
