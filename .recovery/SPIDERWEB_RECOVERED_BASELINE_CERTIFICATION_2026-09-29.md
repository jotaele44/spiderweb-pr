# Spiderweb Floot Recovered Baseline Certification — 2026-09-29

State: **RECOVERED_BASELINE_PASS**
Product certification: **OPEN**
Final-Floot byte identity: **UNRESOLVED / SOURCE UNAVAILABLE**

## Frozen source
- Uploaded ZIP SHA-256: `7746bf2da3fc9a7d59e0e0a495120068e2ec7d15499c7778ff9a8a00fb1c9ad9`
- Exact reconstructed Git tree: `9b493e2ce8f881dee8b49497f0105da8b805a1a4`
- Transport base64 SHA-256: `b02533910bf0e9118a189988b008431132b88111f240552265f8ee13c3cbda98`
- Recovery branch: `recovery/floot-spiderweb-20260929`
- Source ZIP was not modified.

## Recovered application denominator
- 17 canonical routes
- 21 endpoint handlers
- 18 recovered spec files
  - 17 executable
  - 1 empty historical placeholder: `helpers/useDebounce.spec.tsx`
- 9 Kysely table interfaces

## Exact-source executable recovery
GitHub Actions run: `36645830376`
Head: `fea0f69f20ceb65c36ca00470a6e222d575a13f5`
Conclusion: **PASS**

Recovered specs:
- 17/17 executable spec files PASS
- 75/75 executable tests PASS

Reconstruction dependency lock SHA-256:
- `fa989b00921b486edc8e6b08b7355f371a1c9216be71a53cab5195df5ce66ec0`

The lockfile is a **NEW reconstruction manifestation**, not a historical Floot lockfile.

## Endpoint/auth/database regression
- All 21 recovered endpoint handlers enumerated.
- 22/22 recovery regression cases PASS.
- Positive and negative controls cover registration, login, session, logout, account deletion, spatial ACL, layer ownership/editor behavior, feature query, investigations, audit, remote-host allowlisting, authority catalog/collection/geo/status, admin-only pipeline, and certification status.
- Ephemeral PostgreSQL only.
- Historical rows reconstructed: **0**.
- Schema classification: `NEW_NONCANONICAL_TYPE_AND_QUERY_DERIVED_NO_HISTORICAL_ROWS`.
- Unproven historical FK/index/trigger/cascade semantics were not asserted.

Final recovery artifact:
- Artifact ID: `11068910158`
- Artifact digest: `sha256:8451426b2c9227fd31f608a8ccea412984b8b5186c680001f9deff94a6f538f2`

## GitHub lineage
The embedded GitHub lineage is genuine, but it is not source-tree identity:
- `733035df481e231a0df7f306b5a1106b19f27644`
- `ee48d4bb1003c705bf66c5324afa0d76a7e29d91`
- embedded tree at `ee48d4bb...`: `7b7a36193d320aeded110ed67b88ea0f813a34ff`
- Floot ZIP tree: `9b493e2ce8f881dee8b49497f0105da8b805a1a4`

Therefore: `FLOOT_ZIP_TREE != EMBEDDED_GITHUB_TREE`.

## Later Floot evidence
Later chat evidence records Spiderweb states up through 47/47 PASS, including completed acquisition/AOI/source work. Exact later Floot source bytes are unavailable in this recovery input. Those later observations are preserved as reconstruction requirements and must not be used to claim byte identity or to synthesize missing source.

## Certification boundary
PASS applies only to the recovered uploaded Floot baseline under the reconstruction harness and ephemeral database. It does not certify:
- historical production DB contents;
- exact historical dependency graph;
- later 47/47 Floot source identity;
- current production deployment;
- credentials;
- native/physical-device execution;
- unresolved source-owned spatial/acquisition planes.

This receipt permits the sequential recovery vector to advance to MoneySweep without representing Spiderweb as fully production-certified.
