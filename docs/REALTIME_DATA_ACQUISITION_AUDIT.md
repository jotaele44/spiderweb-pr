# Real-Time Data Acquisition — Discovery Audit

> **Advisory only.** Generated 2026-09-23. No acquisition code was changed by
> the commit that introduces this document. Findings are sized so the
> maintainer can approve higher-risk moves (a shared HTTP client, a scheduling
> policy change) deliberately, following the same format as
> [`RECOMMENDATIONS.md`](../RECOMMENDATIONS.md).

## Scope and method

This audit inventories every subsystem that talks to a **live external
source** at runtime (HTTP/REST, OPeNDAP, S3 listing, ArcGIS/OGC Features,
WMS, tile servers) as opposed to subsystems that only read bundled/static
data (`gebco/`, `spiderweb/ingestors/ingest_headstart.py`,
`readiness/satellite_ingest.py` — confirmed out of scope, no network calls).
For each subsystem it records: source/protocol, trigger, resilience
(retry/backoff/timeout/rate limiting), output destination, and provenance.
It then looks across all of them for repeated patterns worth fixing once
instead of N times.

## Inventory: live-acquisition subsystems

| # | Subsystem | Source(s) | Trigger | Retry/backoff | Output |
|---|---|---|---|---|---|
| 1 | `scripts/acquire/noaa_ncei_opendap.py` | NOAA/NCEI THREDDS OPeNDAP | CLI, on-demand | None (single attempt, 30s timeout) | `outputs/` JSON report |
| 2 | `source_adapters/ncei_coastal_dem/` | NCEI OPeNDAP + Coastal LiDAR S3 | Planner only (no HTTP itself) | N/A | `data/ncei_coastal_dem/cache` |
| 3 | `scripts/source_adapters/sdk/` (`DownloadEngine`) | Generic (adapter-supplied) | Library, imported by adapters | None (120s timeout) | adapter `runtime_root` |
| 4 | `scripts/source_adapters/census_partnership_pr/fetch.py` | Census Partnership PR HTML/ZIP | CLI, on-demand | None (60–120s timeout) | `data/raw/census_partnership_pr/` |
| 5 | `scripts/source_adapters/pr_hydrography/` | USGS NHD, USACE NID, ScienceBase, TIGER | CLI + **scheduled** (`pr-hydrography.yml`, weekly, probe-only) | None (single attempt, rich failure classification, no auto-retry) | `data/raw/pr_hydrography/`, `manifests/pr_hydrography/` |
| 6 | `spiderweb/subsurface/adapters.py` | ArcGIS FeatureServer / OGC API Features | Library | None (60s timeout) | caller-specified `snapshot_dir` |
| 7 | `scripts/acquire_pr_archipelago_*.py` (13 scripts) | USGS BGN S3, NOAA InPort, TIGER, PR.gov SIGE, NSDE | CLI + GH Actions, **all `workflow_dispatch`-only** | None (120s timeout) | `evidence/pr_archipelago/source_snapshots/` |
| 8 | `scripts/acquire_jp_flood_documents.py` + `check_jp_flood_live_v3.py` | PR Junta de Planificación HMP portal + municipal PDFs | **Scheduled** (`jp-flood-v3-live-drift.yml`, weekly) | Fallback-URL retry for 2 known-flaky municipalities; resumable download | Orphan branch `jp-flood-v3-receipts` + `artifacts/*.json` |
| 9 | `spiderweb/remote_monitoring/` | (delegates to `imagery/`) | Library | N/A — explicitly out of scope for live pixel fetch | N/A |
| 10 | `imagery/providers/` (Copernicus/Sentinel Hub, NASA GIBS) | STAC search, Process API, WMS | Library, on-demand | **Yes** — 3 retries, `sleep(1.5*(attempt+1))`, retries on 5xx/429 | `tile_cache/imagery/` (content-addressed) |
| 11 | `earthgpt/tiles.py`, `web_context.py` | OSM XYZ tiles, Nominatim | Library, via `run_all.py --earthgpt-*` | **Yes** for tiles (mirrors #10); fail-soft, no-retry for Nominatim | `tile_cache/` |
| 12 | `server/ingestion/ingest_pr_boundaries.py`, `ingest_reference_geo.py`, `ingest_tiger_pr.py` | TIGER, NOAA EEZ, USACE NID, USGS GNIS, USFWS NWI | CLI, on-demand, not wired to any workflow | Partial — 3 retries, **no backoff/sleep** | `data/reference_geo/`, `data/tiger/` |
| 13 | `martin/` + `server/backend/martin_ingress.py` | PostGIS-backed vector tiles via Martin | **Inline in every user tile request** (live reverse proxy) | None (single upstream call, 5s timeout, ETag passthrough) | proxied response |
| 14 | `server/notifications/notifier.py` | Slack webhook, SMTP | On-demand, outbound (not acquisition) | None, deliberately fail-soft | n/a |

## Cross-cutting findings

**1. A shared HTTP SDK exists and is almost entirely unused.**
`scripts/source_adapters/sdk/download.py` (`DownloadEngine` +
`PayloadValidator`) is documented in
`docs/source_adapters/GENERIC_SOURCE_ADAPTER_SDK.md` as the intended reusable
fetch layer, with solid content-type/HTML/ZIP-magic validation and a
`.hold`-on-malformed-response pattern. Grepping for its imports shows **zero
adapters actually use it** — `census_partnership_pr`, `pr_hydrography`,
`pr_archipelago` (13 scripts), `spiderweb/subsurface/adapters.py`, and
`server/ingestion/*` each hand-roll their own near-identical
`urllib.request` fetch-hash-classify logic, down to a nearly-identical
`User-Agent: spiderweb-pr-<adapter>/x.y` string. This is the single largest
duplication-and-drift risk in the acquisition surface: a bug fix or hardening
change (e.g., adding retry) made in one adapter does not propagate to the
other seven.

**2. Retry/backoff quality is inconsistent across three tiers, with no shared implementation.**
- **Tier A (hardened):** `imagery/providers/base.py` and `earthgpt/tiles.py`
  independently implement the *same* retry loop (3 attempts,
  `sleep(1.5*(attempt+1))`, retry on 5xx/429) — deliberately mirrored per
  in-code comments, but copy-pasted rather than shared.
- **Tier B (partial):** `server/ingestion/*` retries 3 times with **no sleep
  between attempts**, which under a real rate-limit or transient 5xx just
  hammers the endpoint 3x faster instead of backing off.
- **Tier C (none):** everything else — `pr_hydrography`, all 13
  `acquire_pr_archipelago_*` scripts, `census_partnership_pr`,
  `spiderweb/subsurface/adapters.py`, `martin_ingress.py` — is a single
  attempt with only a timeout. Several of these (`pr_hydrography/transport.py`)
  have *very* sophisticated failure classification (`RATE_LIMITED`,
  `TIMEOUT`, `PARTIAL_DOWNLOAD`, …) that correctly **detects** a
  retryable condition but then does nothing about it.

**3. No rate limiting anywhere.** Confirmed by grep across all acquisition
code. Combined with finding #2/Tier C, a source returning HTTP 429 is
recorded as a classified failure, not backed off from — repeated scheduled
runs (e.g. weekly `pr-hydrography` probe) could keep tripping the same limit
every cycle with no adaptive delay.

**4. Scheduled (unattended) live re-checks are narrow: 2 of 45 workflows.**
Only `jp-flood-v3-live-drift.yml` (weekly, full acquire+diff+receipt) and
`pr-hydrography.yml` (weekly, metadata-only freshness probe) run on a
recurring `schedule:`. Every `pr-archipelago-*`, `guayama-*`, `w00247-bag`,
and `martin-*` workflow — despite being the largest family of acquisition
code by script count (13 archipelago scripts alone) — is
`workflow_dispatch`-only. Practically: if nobody remembers to manually
re-run these, the checked-in snapshots and receipts can silently drift out
of sync with the live sources indefinitely, and there is no automated signal
that would surface that drift. This is the same pattern the JP-flood and
hydrography workflows were explicitly built to solve for their two domains
— the fix is proven, just not applied elsewhere.

**5. No shared caching layer; freshness policy is ad hoc per adapter.**
`imagery/cache.py` (SHA1 content-addressed) and `earthgpt/tiles.py`
(XYZ-keyed) are real caches with validation-before-reuse. Everywhere else
(`server/ingestion`, `acquire_pr_archipelago_sources.freeze_url`) it's a
simple "does a file already exist at this path" check — idempotent, but with
no TTL/freshness concept, so a stale cached file is indistinguishable from a
fresh one without manually deleting it.

**6. Acquisition-vs-promotion discipline is strong and worth preserving.**
This is not a defect, but it shapes any optimization: `pr_hydrography`,
`acquire_pr_archipelago_*`, and the JP-flood pipeline all draw a hard,
enforced line between "fetched live" and "promoted canonical" (gates,
receipts, `canonical_promotion_permitted: false`, "live observations never
auto-promote frozen source_state"). Any workflow-optimization change (adding
retry, adding scheduling) must not blur this line — retries should only
affect *whether a fetch succeeds*, never *whether its result gets
auto-promoted*.

**7. `docs/DATA_POLICY.md` documents commit hygiene well but has no
acquisition-behavior section.** It's clear on what's never committed and
why, but says nothing about expected timeout/retry/rate-limit behavior for
new adapters — that guidance currently lives only in
`docs/source_adapters/GENERIC_SOURCE_ADAPTER_SDK.md`, which nothing actually
follows (see #1).

## Prioritized recommendations

| # | Area | Recommendation | Effort | Risk | Priority |
|---|------|----------------|--------|------|----------|
| 1 | Consolidate | Extract the retry+backoff loop from `imagery/providers/base.py`/`earthgpt/tiles.py` into one shared helper (e.g. `common/http_retry.py`) both already import; keeps the identical behavior but with one implementation to fix | S | Low | P0 |
| 2 | Harden | Add the same backoff (not just retry count) to `server/ingestion/_download`'s 3-attempt loop — one-line change (`time.sleep` between attempts), removes the "hammer 3x faster" failure mode | S | Low | P0 |
| 3 | Adopt | Migrate at least one of the 8 hand-rolled fetchers (start with `census_partnership_pr/fetch.py`, the smallest) onto `scripts/source_adapters/sdk/download.py` as a proof of adoption; if it fits cleanly, schedule the rest | M | Low | P1 |
| 4 | Reliability | Add basic rate-limit backoff (honor `Retry-After`, or a fixed backoff on the already-detected `RATE_LIMITED` state) to `pr_hydrography/transport.py`'s classifier — the detection logic already exists, only the reaction is missing | S | Medium | P1 |
| 5 | Scheduling | Add a `schedule:` trigger to the `pr-archipelago-*` acquisition workflows (start with `pr-archipelago-acquire.yml`), mirroring the read-only-probe pattern already proven safe in `pr-hydrography.yml` (`canonical_promotion_permitted: false`), so archipelago source drift is caught automatically instead of only on manual dispatch | M | Low | P1 |
| 6 | Documentation | Add an "Acquisition behavior" section to `docs/DATA_POLICY.md` (expected timeout range, when retry/backoff is required, rate-limit handling) and cross-link it from `GENERIC_SOURCE_ADAPTER_SDK.md` so new adapters have one place to check | S | Low | P1 |
| 7 | Observability | Since no rate limiting exists anywhere, add a lightweight per-host request-timestamp check (even an in-memory minimum-interval guard) to the shared retry helper from #1, so any adapter that adopts it gets rate-limit safety for free | M | Low | P2 |

## Quick wins (low effort, low risk)

- **#1** Shared retry/backoff helper — de-duplicates code that is already
  proven correct in two places.
- **#2** Add backoff sleep to `server/ingestion`'s existing retry loop.
- **#6** Document acquisition-behavior expectations in `DATA_POLICY.md`.

## Larger initiatives (plan + sign-off)

- **#3 SDK adoption** — touches live acquisition code paths with real
  external dependencies; validate against each adapter's existing
  provenance/manifest tests before widening beyond the first adopter.
- **#5 scheduling expansion** — increases GitHub Actions minutes and network
  calls against external government/NOAA endpoints; size the rollout
  (one workflow at a time) and confirm each target endpoint tolerates
  weekly probing before enabling broadly.
