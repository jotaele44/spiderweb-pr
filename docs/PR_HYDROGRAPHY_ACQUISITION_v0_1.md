# Puerto Rico Authoritative Hydrography Acquisition Plane v0.1

## Purpose

Make Puerto Rico reservoir/hydrography reconstruction reproducible from Spiderweb without depending on a manually assembled Downloads directory.

The control plane lives in Git. Canonical raw payloads do not.

## Source universes

The acquisition plane keeps source taxonomies and entity universes separate:

- `JURISDICTION_BOUNDARY` — Census TIGER/Line state geometry.
- `NHD_WATERBODY_FEATURE` — USGS NHD waterbody polygons. `FTYPE` is source classification only.
- `NID_DAM_ASSET` — USACE National Inventory of Dams dam assets.
- `USGS_BATHY_SURVEY_FOOTPRINT` — USGS Inland Bathymetric/Topobathymetric survey footprints/events.
- `RESERVOIR_ENTITY` — downstream longitudinal entity layer; it is not equivalent to any source taxonomy above.

`NID_DAM_ASSET != NHD_WATERBODY_FEATURE != RESERVOIR_ENTITY`.

## Frozen v0.1 baseline expectations

These values are regression expectations, never selection rules:

- current PR NHD retained waterbodies: `3213`
- NHD `FTYPE=390`: `2560`
- NHD `FTYPE=436`: `653`
- current NID PR dam assets: `36`
- USGS Inland Bathymetry v4 PR survey footprints: `6`
- V4-to-NID explicit hard bindings: `5`

A future authoritative refresh may legitimately change these values. Such a change creates a new snapshot and requires adjudication; code must not filter data to force historical counts.

## Snapshot contract

Every acquired payload is written under a content-addressed immutable runtime path and receives:

- source ID
- authority and source universe
- adapter version
- deterministic request signature
- upstream update marker when available
- byte count and SHA-256
- schema fingerprint
- acquisition timestamp
- parent snapshot
- payload path
- snapshot state

The snapshot store refuses to overwrite an existing snapshot directory.

Recommended runtime root:

```text
data/raw/pr_hydrography/
```

This path is runtime data and must remain outside Git-tracked canonical source control. Small source registries, tests, and certification manifests may be promoted separately.

## Source registry

Version-controlled registry:

```text
manifests/pr_hydrography/source_registry.csv
```

Initial authoritative adapters:

1. Census TIGER/Line 2025 state boundary archive.
2. USGS NHD `Waterbody - Large Scale` layer 12.
3. USACE NID public FeatureServer layer 0.
4. USGS ScienceBase Inland Bathymetry v4 canonical GDB ZIP resolved from item metadata.

## Commands

Write/rebuild the source registry:

```bash
python -m scripts.source_adapters.pr_hydrography.cli write-source-registry
```

Pull one source:

```bash
python -m scripts.source_adapters.pr_hydrography.cli pull-source --source nhd
python -m scripts.source_adapters.pr_hydrography.cli pull-source --source nid
python -m scripts.source_adapters.pr_hydrography.cli pull-source --source tiger
python -m scripts.source_adapters.pr_hydrography.cli pull-source --source inland-bathy
```

Pull all registered hydrography sources:

```bash
python -m scripts.source_adapters.pr_hydrography.cli pull-hydrography --source all
```

Refresh and create a new snapshot only when changed:

```bash
python -m scripts.source_adapters.pr_hydrography.cli refresh-changed --source all
```

A schema fingerprint change fails closed as `BLOCKED_SCHEMA_DRIFT`.

## Certification doctrine

### Raw strings

Raw source strings are preserved. Mojibake repair and accent/case folding occur only in matching representations.

### CSV header/preamble

Tabular readers detect the header from required schema fields. A metadata preamble such as the NID `Data Last Updated:` line must not be mistaken for the header.

### Boolean fields

CSV text is parsed explicitly. `bool("False")` semantics are prohibited.

### Geometry

Invalid source geometry is preserved. `make_valid` is allowed only for a separate analysis geometry. Validation records source validity, analysis validity, repair state, geometry types, areas, and Hausdorff distance. Source geometry must remain byte/logically unchanged.

### Candidate resolution

Cross-source candidate sets follow:

```text
candidate_set = bounded_discovery_candidates UNION explicit_higher_grade_evidence
```

Therefore a discovery radius cannot erase an authoritative binding. Caonillas is the frozen regression case: the V4/NHD hard-bound polygon remains eligible even when it is outside the 2.5 km discovery radius.

Prohibited shortcuts:

- nearest candidate as identity
- NHD `FTYPE` as reservoir identity
- deterministic ordering as evidence
- distance as a tiebreaker when evidence rank is equal
- columnwise row synthesis such as `groupby().first()` for winner construction

Top-evidence ties remain `TOP_EVIDENCE_TIE_REVIEW`. Distance-only candidates remain unresolved.

## CI and freshness probes

`.github/workflows/pr-hydrography.yml` runs offline regressions for code changes. A scheduled/manual freshness job probes authoritative endpoints and uploads a short-lived report.

A GitHub Actions artifact is **not** a canonical source-byte archive. Full source acquisition must write to persistent runtime/object storage controlled by the operator. Ephemeral CI storage may never be the only copy of canonical raw bytes.

## v0.1 migration boundary

The v0.1 package establishes the acquisition/snapshot/certification contracts and offline regressions. The existing manually certified reservoir artifacts remain historical evidence until their exact source bytes are ingested into registered Spiderweb snapshots and their hashes match the prior frozen manifests.

Do not claim migration complete solely because the new adapters reproduce the historical denominators. Byte-level provenance must be bound where prior hashes exist.
