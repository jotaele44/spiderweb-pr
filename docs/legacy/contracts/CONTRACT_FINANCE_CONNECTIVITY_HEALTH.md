# Contract-Finance Connectivity Health — moneysweep-pr → spiderweb-pr

**Assessed:** 2026-05-28 · **Re-verified after fix:** 2026-05-29
**Scope:** the *financial data handoff* — the federation **export package** that
moneysweep-pr (producer) ships and the spiderweb-pr `contract_finance` layer
(consumer) ingests.

## Status

| | Before | After (this change) |
|---|---|---|
| Handoff | 🔴 **BROKEN** | 🟢 **HEALTHY** |
| Shared contract version | `1.1.0` on both labels — but two incompatible definitions | `1.2.0`, single shared shape on both |
| Producer sample → consumer adapter | **rejected** at 2 hard gates | loads, gate `READY`, layer scores |
| Drift guard | none | byte-identical conformance fixture + tests in both repos |

## Topology

```
moneysweep-pr (producer)                         spiderweb-pr (consumer / query hub)
  scripts/build_export_package.py                     federation/hub/adapters/moneysweep.py
  schemas/moneysweep_*.schema.json   ── pkg ─►   readiness/moneysweep_package_gate.py
  exports/ (manifest.json + 5 *.jsonl)                 readiness/contract_finance_layer.py
                                                       (registered: federation/hub/layer_registry.py)
```

The package is a directory: `manifest.json` + five JSONL streams
(`entities`, `sources`, `funding_awards`, `transactions`, `relationships`).

## What was broken (root cause)

Both repos were pinned to export-contract **`1.1.0`**, but each had independently
defined an *incompatible* "1.1.0" shape, and there was **no cross-repo conformance
test** — the matching version string masked the drift. Each repo's CI only
exercised its own fixture (the consumer's `tests/fixtures/moneysweep_v1_1/`
encoded a shape moneysweep-pr never emits).

Running the consumer's own validators against the producer's shipped
`exports/samples/` reproduced two hard failures plus quieter divergences:

1. **Manifest topology (HARD FAIL).** Producer emits `manifest["files"]` (array of
   `{filename, stream, record_count, sha256, schema_id}`); consumer required
   `manifest["streams"]` (object). →
   `ContractSweeperAdapterError: manifest.streams must be an object`.
2. **Money-row entity reference (HARD FAIL).** Producer ships dual refs
   (`recipient_entity_id` + `funding_agency_entity_id` on awards;
   `payer_entity_id` + `payee_entity_id` on transactions); consumer required a
   single `entity_id`. →
   `ContractSweeperAdapterError: funding_awards row missing text field: entity_id`.
3. **Coordinate keys (silent data loss).** Producer uses `location.latitude` /
   `location.longitude`; consumer read `location.lat` / `location.lon`, so every
   point geometry would have been dropped.
4. **Soft.** Entity display name `name` (producer) vs `raw_name` (consumer);
   `lineage` object shape differs (both truthy, so the gate's lineage check passed).
5. **Hazard (not on the wire).** moneysweep-pr's
   `moneysweep/federation/{envelope,export_writer,validator}.py` is a separate
   *evidence-envelope* track (`schema_version "0.1"`) that matches neither the
   shipped package nor the consumer. It is decoupled from `build_export_package.py`
   and has been annotated to prevent confusion.

## The fix — shared v1.2.0 contract

Canonical = the producer's schema-backed shape (richer; already enforced by
moneysweep-pr's `scripts/validate_export.py`). Both repos bumped `1.1.0 → 1.2.0`
(a coordination bump; no field changes vs. the producer's real 1.1.0).

**Producer (moneysweep-pr):** version bump in `scripts/build_export_package.py`,
`schemas/moneysweep_export_manifest.schema.json`, `exports/samples/`, docs;
legacy envelope track annotated; new non-synthetic conformance package committed at
`exports/conformance/v1_2/`.

**Consumer (spiderweb-pr):** `federation/hub/adapters/moneysweep.py` now reads
the `files[]` manifest, the dual entity refs (using `recipient_entity_id` /
`payee_entity_id` as the primary entity and carrying the counterparty), and
`latitude`/`longitude` (with `lat`/`lon` fallback). `EXPECTED_VERSION = "1.2.0"`;
`readiness/moneysweep_package_gate.py` reads the canonical coordinates;
`federation/hub/layer_registry.py` pinned to `1.2.0`. Downstream scoring
(`contract_finance_layer` / `_calibration` / `_fusion`) is unchanged — it consumes
the adapter's `properties.entity_id`, which is still populated.

## Drift guard (anti-regression)

- A single **non-synthetic v1.2.0 conformance package**, byte-identical in both repos:
  - producer: `exports/conformance/v1_2/`
  - consumer: `tests/fixtures/moneysweep_v1_2/`
- `tests/test_moneysweep_conformance.py` (consumer): loads it in **production**
  mode → gate `READY` → layer scores; asserts both version pins are `1.2.0`.
- `scripts/federation_conformance_check.py` (consumer): when both repos are
  co-located, builds a package with the producer's own build script and ingests it
  through the consumer — proving the live round-trip (skips gracefully in
  separate-repo CI).

## Verification performed

- Producer: `python scripts/smoke_export.py` ✓; `scripts/validate_export.py
  --mode production` on the conformance package ✓; full `pytest` 1174 passed.
- Consumer: full `pytest` 738 passed (unrelated `fastapi`/`scipy`/`xarray` modules
  skipped); conformance + contract-finance tests green.
- Live round-trip: `scripts/federation_conformance_check.py` →
  `[OK] ... mode=production gate=READY layer=READY records=3`.
