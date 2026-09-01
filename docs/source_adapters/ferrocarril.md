# Ferrocarril ILAP source adapter

## Purpose

Integrate the Puerto Rico Ferrocarril ILAP research dataset into Spiderweb-PR without collapsing source classifications, historical entities, and analytical candidates into one canonical layer.

The adapter treats the current Ferrocarril master as a **versioned provisional source snapshot**. It preserves the source's F1-F8 subtype vocabulary and E1/E2/E3 evidence labels verbatim, but does not treat those labels as Spiderweb certification.

## Input

Operator-local CSV:

```text
data/sources/ferrocarril/ferrocarril_ilap_master_full.csv
```

The raw CSV is intentionally not committed. This follows `docs/DATA_POLICY.md`.

Snapshot currently bound in `configs/ferrocarril_source.yaml`:

- SHA256: `1241049696f4d452b3bcbd4ad7d834476dccff64daa38847b53685109922366f`
- rows: `609`
- subtype counts: F1=77, F2=101, F3=206, F4=85, F5=22, F6=47, F7=24, F8=47
- source evidence counts: E1=596, E2=11, E3=2
- exact coordinates: 0/609 in the reviewed snapshot

These counts are snapshot facts. They supersede conversational claims that every row was already E1 or exactly georeferenced.

## Output

Running:

```bash
python scripts/ferrocarril_ingest.py
```

writes runtime artifacts under `outputs/`:

- `ferrocarril_ilap_candidates.geojson`
- `ferrocarril_ilap_manifest.json`

The GeoJSON keeps records with unresolved coordinates using `geometry: null`. Coordinates are never synthesized.

## Identity and certification policy

The current source mixes several universes that must remain distinct until proven equivalent:

1. historical source records;
2. historical rail entities/assets;
3. analytical ROW/corridor features;
4. candidate or inferred infrastructure.

Accordingly every imported row is initially:

```text
certification_state = PROVISIONAL
fact_status = inferred
```

A source `Status=E1` means only that the source snapshot classifies the row E1. It does **not** automatically mean `CERTIFIED` in Spiderweb-PR.

Promotion to a canonical Ferrocarril entity requires, at minimum:

- row-level documentary provenance or an authoritative historical binding;
- validated coordinates or certified geometry;
- duplicate/collision adjudication;
- preservation of contradictory observations;
- no unresolved 1:N or N:1 identity ambiguity;
- arithmetic closure for source/retained/excluded counts.

## F1-F8 source vocabulary

The adapter preserves the source subtype field verbatim:

- F1 — mainline / station / principal alignment
- F2 — halt / parada
- F3 — spur / branch / tramway
- F4 — culvert / drainage crossing
- F5 — bridge / tunnel portal / major crossing
- F6 — yard / industrial complex / sorting node
- F7 — port / wharf interface
- F8 — urban mask / buried ROW / road conversion

The subtype is source taxonomy, not canonical identity.

## Validation gates

The adapter fails closed when:

- required columns are missing;
- source IDs are duplicated;
- a subtype falls outside F1-F8;
- only one coordinate of a lat/lon pair is present;
- coordinates fall outside the Puerto Rico bounding guardrail.

Regression tests are in `tests/test_ferrocarril_ingest.py`.

## Next certification pass

The next pass should attach a row-level evidence table with source URI/archive reference, retrieval date, source type, exact geometry status, and identity adjudication state. Until that pass is complete, downstream scoring may use the Ferrocarril layer as a provisional analytical input but should not treat proximity to a row as proof of a historical rail asset or subsurface structure.
