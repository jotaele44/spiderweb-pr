# Spiderweb-PR Self-Auditing Implementer

Repository-native control skill for finishing `jotaele44/spiderweb-pr` through bounded, test-backed, self-audited changes.

## Safety boundary

Version 0.1 may modify only this skill package. It does not install itself, modify product code, merge branches, or promote releases. Later product-code work requires a separately approved vector.

## Audit cycle

1. Resolve repository and branch authority.
2. Inventory code, tests, schemas, documentation, CI, issues, and open PRs.
3. Reconstruct a measurable baseline.
4. Reconcile backlog claims against implementation evidence.
5. Select one unblocked atomic task.
6. Define acceptance and regression tests.
7. Implement on an isolated branch.
8. Run focused and CI-equivalent validation.
9. Audit boundaries, test integrity, data policy, schemas, determinism, and completion truth.
10. Certify only when every mandatory gate passes.

## Local package validation

```bash
cd skills/spiderweb-pr-self-auditing-implementer
python -m pytest -q
```

## Completion rule

A task is complete only when implementation, acceptance tests, regression tests, schema contracts, boundary audit, documentation reconciliation, and CI-equivalent validation all pass with zero material contradictions and zero unresolved required inputs.
