---
name: spiderweb-pr-unified-live-skillpack
description: "Compiled non-activating dispatch contract for shared and spiderweb-pr capabilities."
version: 1.0.0
compatibility: claude
repository: spiderweb-pr
---

# spiderweb-pr Unified Live Skillpack

Pinned base: `ed12141c3cb6480846c859e5780242a62ae71283`.

## Execution contract

- Exact capability identifiers only; unknown identifiers fail closed.
- Runtime activation, automatic dispatch, live polling, notifications, external writes, promotion, control actions, merge, and release are disabled.
- Source module semantics remain cryptographically bound in `MANIFEST.json`; this file is the compiled live dispatcher.
- Repository-specific authority overrides shared defaults.

## Capability dispatch

| Capability | Module | Status | Preserved responsibility |
|---|---|---|---|
| `repo-state-reader` | `repository-governance` | `` |  |
| `repo-identity-guard` | `repository-governance` | `` |  |
| `branch-guard` | `repository-governance` | `` |  |
| `task-scope-guard` | `repository-governance` | `` |  |
| `git-action-guard` | `repository-governance` | `` |  |
| `skill-authoring-template` | `skill-lifecycle` | `` |  |
| `skill-package-builder` | `skill-lifecycle` | `` |  |
| `validation-gate-runner` | `validation-and-recovery` | `` |  |
| `failure-packet-builder` | `validation-and-recovery` | `` |  |
| `delta-reporter` | `reporting-and-receipts` | `` |  |
| `status-writer` | `reporting-and-receipts` | `` |  |
| `foia-correspondence-manager` | `foia-operations` | `` |  |
| `foia-request-sender` | `foia-operations` | `` |  |
| `spiderweb-operator` | `orchestration-and-repository-ops` | `` |  |
| `spiderweb-repo-inventory` | `orchestration-and-repository-ops` | `` |  |
| `spiderweb-pipeline` | `orchestration-and-repository-ops` | `` |  |
| `spiderweb-github-pr` | `orchestration-and-repository-ops` | `` |  |
| `spiderweb-ios-ashell` | `orchestration-and-repository-ops` | `` |  |
| `spiderweb-pr-workflow-optimizer` | `orchestration-and-repository-ops` | ``; alias of `spiderweb-operator` |  |
| `spiderweb-gis-layer-intake` | `geospatial-intake-and-normalization` | `` |  |
| `spiderweb-spatial-normalization` | `geospatial-intake-and-normalization` | `` |  |
| `spiderweb-usgs-geology-intake` | `geospatial-intake-and-normalization` | `` |  |
| `spiderweb-overlay-analysis` | `overlay-and-review` | `` |  |
| `spiderweb-review-queue` | `overlay-and-review` | `` |  |
| `spiderweb-data-validation` | `validation-and-export` | `` |  |
| `spiderweb-export-validator` | `validation-and-export` | `` |  |
| `spiderweb-build-test-execution` | `build-and-failure` | `` |  |
| `spiderweb-failure-triage` | `build-and-failure` | `` |  |

## Required output fields

Every execution receipt must include `capability_id`, `repository`, `pinned_base_commit`, `inputs`, `outputs`, `validation`, `limitations`, `authority`, and `next_action`.

## Non-activation boundary

This binding does not invoke repository code. A later runtime adapter requires separate design, tests, review, and explicit authorization.
