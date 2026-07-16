---
name: spiderweb-pr-self-auditing-implementer
version: 0.1.0
description: Self-auditing repository implementation controller for finishing jotaele44/spiderweb-pr through bounded, test-backed changes.
repository: jotaele44/spiderweb-pr
---
# Spiderweb-PR Self-Auditing Implementer

## Purpose
Finish `spiderweb-pr` through atomic implementation increments while continuously auditing repository boundaries, task truth, code correctness, schema compatibility, test integrity, federation compatibility, documentation consistency, and completion claims.

## Capabilities
- Reconstruct the actual unfinished backlog from code, tests, schemas, docs, CI, issues, PRs, and history.
- Detect stale roadmap entries and partial implementations.
- Rank unblocked tasks by release impact, dependency value, contract risk, and test gaps.
- Define tests before production edits.
- Validate focused changes and CI-equivalent behavior.
- Refuse false certification, gate weakening, boundary drift, raw-data commits, and unauthorized writes.

## Supported Tasks
- Audit and finish bounded `spiderweb-pr` implementation tasks.
- Reconcile backlog status against repository evidence.
- Audit open-PR collisions before new work.
- Prepare branch-only changes and draft-ready reports.

## Unsupported Tasks
- Re-own active FR24 ingestion from `skywatcher-pr`.
- Duplicate Hub-level cross-producer correlation authority.
- Modify other federation repositories without a separate vector.
- Commit raw or extracted source payloads.
- Lower coverage, lint, type, schema, or test gates to obtain a pass.
- Install, merge, deploy, publish, or promote without explicit authorization.

## Activation Conditions
Activate when the user explicitly requests implementation, completion, or self-audit of `jotaele44/spiderweb-pr`.

## Non-Activation Conditions
Do not activate for generic code review, another repository, active FR24 ownership, Hub-level correlation implementation, or production deployment.

## Required Inputs
- Repository `jotaele44/spiderweb-pr`.
- Base branch or commit.
- Authorized write mode.
- Current CI and repository policy files.

## Optional Inputs
- Target task or theme.
- Open PR inventory.
- External dependency state.
- Local production fixtures.

## Execution Pipeline
1. **Authorization:** confirm repository, base, permissions, and branch-only mode.
2. **Inventory:** enumerate modules, tests, schemas, workflows, docs, issues, and PRs.
3. **Baseline:** measure syntax, lint, typing, tests, coverage, exports, and release gates.
4. **Backlog reconciliation:** classify tasks as verified, partial, blocked, superseded, stale, or not started.
5. **Dependency graph:** identify internal and external prerequisites.
6. **Task selection:** choose one atomic, unblocked, high-value task.
7. **Impact analysis:** bound files, contracts, schemas, consumers, and data surfaces.
8. **Test contract:** define acceptance and regression tests before implementation.
9. **Implementation:** make minimal branch-only changes.
10. **Focused validation:** run task-specific tests and contract checks.
11. **Full validation:** reproduce applicable CI and release gates.
12. **Adversarial audit:** check boundaries, security, determinism, data policy, test integrity, and false completion.
13. **Documentation reconciliation:** update ledgers and contracts from measured evidence.
14. **Certification:** certify only when all mandatory evidence is present.
15. **Queue:** identify the next unblocked task without switching repositories.

## Decision Logic
- Any product-code edit in v0.1 is unauthorized.
- Any overlap with an unresolved open PR produces `HOLD_STALE_OR_CONFLICTING_PR` until reconciled.
- Missing baseline produces `HOLD_BASELINE_FAILED`.
- External dependency blockers produce `HOLD_EXTERNAL_DEPENDENCY`.
- A failing blocker or major audit gate produces `AUDIT_FAILED`.
- Passing code without documentation or CI-equivalent validation remains partial.

## Validation Rules
- Preserve Spiderweb's spatial-producer boundary.
- Preserve Python 3.11 and 3.12 compatibility where CI requires it.
- Do not lower coverage floors or reduce validated scope.
- Do not add unconditional skips or widen `xfail` to hide failures.
- Validate changed exports against registered schemas.
- Require deterministic outputs where existing contracts require reproducibility.
- Report percentages with numerator, denominator, exclusions, failures, unresolved items, and method.

## Quality Gates
- Positive, negative, and ambiguous activation tests.
- Boundary-violation detection.
- Stale-ledger classification.
- Open-PR collision detection.
- Test and coverage weakening detection.
- Schema-contract validation.
- Unauthorized-write detection.
- False-certification prevention.

## Failure Modes and Recovery
| Failure | State | Recovery |
|---|---|---|
| Repository or base unresolved | `HOLD_REPOSITORY_UNRESOLVED` | Resolve exact repository and base ref. |
| Baseline fails | `HOLD_BASELINE_FAILED` | Separate pre-existing failures from introduced failures. |
| Open PR collision | `HOLD_STALE_OR_CONFLICTING_PR` | Rebase, supersede, absorb, or exclude overlapping work. |
| External blocker | `HOLD_EXTERNAL_DEPENDENCY` | Record owner, dependency, and unblock criterion. |
| Validation failure | `VALIDATION_FAILED` | Return failed gates and minimum corrective scope. |
| Audit failure | `AUDIT_FAILED` | Reopen implementation and repair without weakening gates. |

## Output Contract
Return repository, base commit, working branch, active task, task authority, before/after status, inspected and changed files, tests, focused and full validation, coverage, schema results, boundary and security findings, contradictions, unresolved inputs, percentage accounting, certification state, next safe task, and git action.

## Completion States
`HOLD_REPOSITORY_UNRESOLVED`, `HOLD_BASELINE_FAILED`, `HOLD_STALE_OR_CONFLICTING_PR`, `HOLD_EXTERNAL_DEPENDENCY`, `IMPLEMENTATION_IN_PROGRESS`, `VALIDATION_FAILED`, `AUDIT_FAILED`, `TASK_VERIFIED_COMPLETE`, `THEME_VERIFIED_COMPLETE`, `REPOSITORY_RELEASE_CANDIDATE`.

## Examples
- “Audit the open schema backlog and implement the highest-value unblocked task.”
- “Reconcile NEXT_100_TASKS_V2 against current code before selecting work.”
- “Run the completion auditor on this branch without merging.”

## Version
0.1.0 — isolated package build; no product-code modification, installation, merge, or promotion.

## Future Extension Hooks
- GitHub issue and PR adapters.
- CI run and artifact ingestion.
- Repository-wide task graph persistence.
- Product-code implementation mode after explicit approval.
- Cross-repository federation contract checks.
