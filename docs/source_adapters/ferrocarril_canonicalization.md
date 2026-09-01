# Ferrocarril canonicalization

This workflow is the promotion stage after `scripts/ferrocarril_ingest.py`.
It does **not** treat source `E1` as Spiderweb `CERTIFIED` and does not fill missing coordinates by centroid, nearest-name, or proximity heuristics.

## Universes

- `FERROCARRIL_SOURCE`: every frozen source observation, preserved 1:1 from the provisional ingest universe.
- `FERROCARRIL_CANONICAL`: only adjudicated historical entities that satisfy the promotion gate.
- `FERROCARRIL_ANALYTICAL`: useful reconstructed/noncanonical linear or corridor features that must not be represented as historical entities.

Source-row count and canonical-entity count are independent universes and are not expected to match.

## Adjudication CSV

Operator-local path:

`data/sources/ferrocarril/ferrocarril_adjudication.csv`

Required columns:

- `feature_id`
- `certification_state`
- `coordinate_status`
- `provenance_locator`
- `provenance_type`
- `identity_relation`
- `canonical_id`
- `latitude`
- `longitude`
- `adjudication_notes`

Allowed identity relations are `1:1`, `1:N`, `N:1`, `N:N`, `0:1`, and `UNRESOLVED`.

Allowed coordinate states are `EXACT`, `BOUNDED`, `APPROXIMATE`, and `UNRESOLVED`.

## Promotion gate

A row may become `CERTIFIED` only when all of the following are true:

1. `provenance_locator` is non-empty.
2. `canonical_id` is non-empty.
3. Identity relation is resolved.
4. Coordinate status is `EXACT` or `BOUNDED`.
5. Point coordinates are present and inside Puerto Rico bounds.
6. Any canonical-ID collision is explicitly adjudicated as `N:1` or `N:N`.

`APPROXIMATE` geometry is useful for discovery but cannot support `CERTIFIED` promotion.
`UNRESOLVED` coordinate state must carry null geometry.

## Fail-closed invariants

The canonicalization script rejects:

- missing adjudication rows for any source feature;
- adjudication rows referring to unknown source IDs;
- duplicate source or adjudication IDs;
- partial latitude/longitude pairs;
- coordinates outside Puerto Rico bounds;
- certified rows without provenance;
- certified rows without canonical IDs;
- certified rows with unresolved identity;
- asserted geometry under `UNRESOLVED` coordinate state;
- duplicate canonical IDs unless the crosswalk explicitly allows many-to-one or many-to-many identity.

The script asserts row conservation between `FERROCARRIL_SOURCE` and the crosswalk.

## Outputs

- `outputs/ferrocarril_source.geojson`
- `outputs/ferrocarril_canonical.geojson`
- `outputs/ferrocarril_analytical.geojson`
- `outputs/ferrocarril_crosswalk.csv`
- `outputs/ferrocarril_canonicalization_manifest.json`

These outputs are intentionally **not yet registered in `schemas/schema_index.json`**. Registration belongs to the release-contract phase after the exact output contracts and canonical ID conventions are frozen.

## Current blocker

The frozen 609-row source snapshot contains no exact coordinates and no row-level documentary bindings. The scaffold enables deterministic promotion when evidence is attached, but it does not create that evidence.
