---
name: spiderweb-pr-unified-live-skillpack
description: "Compiled non-activating dispatch contract."
version: 1.0.1
compatibility: claude
repository: spiderweb-pr
---

# spiderweb-pr Unified Live Skillpack

Pinned base: `ed12141c3cb6480846c859e5780242a62ae71283`.

## Execution contract

- Exact identifiers only; unknown identifiers fail closed.
- Runtime activation, automatic dispatch, polling, notifications, writes, promotion, control, merge, and release are disabled.
- Module and package hashes remain in `MANIFEST.json`.

## Capability dispatch

| Capability | Module | Status | Preserved responsibility |
|---|---|---|---|
<a id="capability-repo-state-reader"></a>| `repo-state-reader` | `repository-governance` | `preserved-active-contract` | Preserve `repo-state-reader` under `repository-governance`. |
<a id="capability-repo-identity-guard"></a>| `repo-identity-guard` | `repository-governance` | `preserved-active-contract` | Preserve `repo-identity-guard` under `repository-governance`. |
<a id="capability-branch-guard"></a>| `branch-guard` | `repository-governance` | `preserved-active-contract` | Preserve `branch-guard` under `repository-governance`. |
<a id="capability-task-scope-guard"></a>| `task-scope-guard` | `repository-governance` | `preserved-active-contract` | Preserve `task-scope-guard` under `repository-governance`. |
<a id="capability-git-action-guard"></a>| `git-action-guard` | `repository-governance` | `preserved-active-contract` | Preserve `git-action-guard` under `repository-governance`. |
<a id="capability-skill-authoring-template"></a>| `skill-authoring-template` | `skill-lifecycle` | `preserved-active-contract` | Preserve `skill-authoring-template` under `skill-lifecycle`. |
<a id="capability-skill-package-builder"></a>| `skill-package-builder` | `skill-lifecycle` | `preserved-active-contract` | Preserve `skill-package-builder` under `skill-lifecycle`. |
<a id="capability-validation-gate-runner"></a>| `validation-gate-runner` | `validation-and-recovery` | `preserved-active-contract` | Preserve `validation-gate-runner` under `validation-and-recovery`. |
<a id="capability-failure-packet-builder"></a>| `failure-packet-builder` | `validation-and-recovery` | `preserved-active-contract` | Preserve `failure-packet-builder` under `validation-and-recovery`. |
<a id="capability-delta-reporter"></a>| `delta-reporter` | `reporting-and-receipts` | `preserved-active-contract` | Preserve `delta-reporter` under `reporting-and-receipts`. |
<a id="capability-status-writer"></a>| `status-writer` | `reporting-and-receipts` | `preserved-active-contract` | Preserve `status-writer` under `reporting-and-receipts`. |
<a id="capability-foia-correspondence-manager"></a>| `foia-correspondence-manager` | `foia-operations` | `preserved-active-contract` | Preserve `foia-correspondence-manager` under `foia-operations`. |
<a id="capability-foia-request-sender"></a>| `foia-request-sender` | `foia-operations` | `preserved-active-contract` | Preserve `foia-request-sender` under `foia-operations`. |
<a id="capability-spiderweb-operator"></a>| `spiderweb-operator` | `orchestration-and-repository-ops` | `preserved-active-contract` | Preserve `spiderweb-operator` under `orchestration-and-repository-ops`. |
<a id="capability-spiderweb-repo-inventory"></a>| `spiderweb-repo-inventory` | `orchestration-and-repository-ops` | `preserved-active-contract` | Preserve `spiderweb-repo-inventory` under `orchestration-and-repository-ops`. |
<a id="capability-spiderweb-pipeline"></a>| `spiderweb-pipeline` | `orchestration-and-repository-ops` | `preserved-active-contract` | Preserve `spiderweb-pipeline` under `orchestration-and-repository-ops`. |
<a id="capability-spiderweb-github-pr"></a>| `spiderweb-github-pr` | `orchestration-and-repository-ops` | `preserved-active-contract` | Preserve `spiderweb-github-pr` under `orchestration-and-repository-ops`. |
<a id="capability-spiderweb-ios-ashell"></a>| `spiderweb-ios-ashell` | `orchestration-and-repository-ops` | `preserved-active-contract` | Preserve `spiderweb-ios-ashell` under `orchestration-and-repository-ops`. |
<a id="capability-spiderweb-pr-workflow-optimizer"></a>| `spiderweb-pr-workflow-optimizer` | `orchestration-and-repository-ops` | `compatibility-alias` | Preserve `spiderweb-pr-workflow-optimizer` as an alias of `spiderweb-operator`. |
<a id="capability-spiderweb-gis-layer-intake"></a>| `spiderweb-gis-layer-intake` | `geospatial-intake-and-normalization` | `preserved-active-contract` | Preserve `spiderweb-gis-layer-intake` under `geospatial-intake-and-normalization`. |
<a id="capability-spiderweb-spatial-normalization"></a>| `spiderweb-spatial-normalization` | `geospatial-intake-and-normalization` | `preserved-active-contract` | Preserve `spiderweb-spatial-normalization` under `geospatial-intake-and-normalization`. |
<a id="capability-spiderweb-usgs-geology-intake"></a>| `spiderweb-usgs-geology-intake` | `geospatial-intake-and-normalization` | `preserved-active-contract` | Preserve `spiderweb-usgs-geology-intake` under `geospatial-intake-and-normalization`. |
<a id="capability-spiderweb-overlay-analysis"></a>| `spiderweb-overlay-analysis` | `overlay-and-review` | `preserved-active-contract` | Preserve `spiderweb-overlay-analysis` under `overlay-and-review`. |
<a id="capability-spiderweb-review-queue"></a>| `spiderweb-review-queue` | `overlay-and-review` | `preserved-active-contract` | Preserve `spiderweb-review-queue` under `overlay-and-review`. |
<a id="capability-spiderweb-data-validation"></a>| `spiderweb-data-validation` | `validation-and-export` | `preserved-active-contract` | Preserve `spiderweb-data-validation` under `validation-and-export`. |
<a id="capability-spiderweb-export-validator"></a>| `spiderweb-export-validator` | `validation-and-export` | `preserved-active-contract` | Preserve `spiderweb-export-validator` under `validation-and-export`. |
<a id="capability-spiderweb-build-test-execution"></a>| `spiderweb-build-test-execution` | `build-and-failure` | `preserved-active-contract` | Preserve `spiderweb-build-test-execution` under `build-and-failure`. |
<a id="capability-spiderweb-failure-triage"></a>| `spiderweb-failure-triage` | `build-and-failure` | `preserved-active-contract` | Preserve `spiderweb-failure-triage` under `build-and-failure`. |

## Required receipt fields

`capability_id`, `repository`, `pinned_base_commit`, `inputs`, `outputs`, `validation`, `limitations`, `authority`, and `next_action`.

## Non-activation boundary

This binding does not invoke repository code. Runtime adapters require separate authorization.
