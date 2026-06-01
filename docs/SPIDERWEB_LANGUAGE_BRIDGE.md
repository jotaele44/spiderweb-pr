# Spiderweb Language Bridge

Canonical terminology for the Spiderweb intake layer. Operators and downstream graph consumers should agree on these terms; producers reading natural-language source data must map to the canonical IDs before emitting Spiderweb observations.

This is the **vocabulary contract** between the OCR/extraction layer and the downstream Spiderweb graph.

---

## Canonical entity types

| Canonical ID | Meaning | Where it's produced |
|---|---|---|
| `POI` | Point of interest — a discrete location worth a node. | `airspace_poi_candidates.geojson`; OCR labels promoted to `labeled_pois` table |
| `ILAP` | Intra-Lateral Asymmetric Path — a recurring flight track that's notably non-direct (loiter, orbit, hover, off-corridor curves). | `airspace_ilap_candidates.geojson` produced by `integration/ilap_airspace_bridge.py` |
| `AASB` | Airport-Anchored Surface Bridge — an edge between two known airports derived from flight pairs (`from_node`, `to_node` ∈ {SJU, BQN, PSE, SIG, NRR, MAZ, ARE, CPX, VQS}). | `aasb_airspace_edges.csv` produced by `integration/aasb_airspace_bridge.py` |
| `corridor` | A repeated air-route pattern between known nodes, scored on recurrence + loiter + infra-alignment. | `airspace_corridor_candidates.geojson` |
| `hydro` | A hydrological overlay reference (river, coastline, harbor) that a POI or corridor passes through/over. | scored by `readiness/spiderweb_intake.py::_score_hydro` |
| `utility` | A utility-infrastructure reference (power line, antenna, tank, substation) intersected. | scored by `readiness/spiderweb_intake.py::_score_utility` |
| `industrial` | An industrial-facility cluster (factory, plant, quarry) intersected. | inferred from `unlabeled_poi_candidates.candidate_type` (`facility_cluster`, `quarry`, `tank`) |
| `municipal_boundary` | Distance to the nearest of 72 PR-municipal centroids — a coarse proximity-to-town signal. | `readiness/spiderweb_intake.py::MUNICIPAL_CENTROIDS` |
| `airspace` | The umbrella container; everything else lives inside an airspace context (see `airspace_*.geojson`). | `integration/aasb_airspace_bridge.py` + `integration/ilap_airspace_bridge.py` |

---

## MBIL (Maximum Built-Infrastructure Load) classes

MBIL is the scoring vocabulary for "how built-up is the area around this candidate." It's computed by [`readiness/spiderweb_intake.py::_score_mbil`](../readiness/spiderweb_intake.py).

| Class | Meaning | Typical score range |
|---|---|---|
| `MBIL-0` | Effectively wilderness — no nearby built infrastructure detected. | 0.00–0.10 |
| `MBIL-1` | Sparse — rural homestead density, isolated structures. | 0.10–0.30 |
| `MBIL-2` | Moderate — village density, multiple roads, light commercial. | 0.30–0.55 |
| `MBIL-3` | Dense — urban/peri-urban, multiple infrastructure layers stacked. | 0.55–1.00 |

**MBIL-X** — meaning **unclassified** — fires when a candidate cannot be meaningfully scored on the municipal-proximity axis:
- Missing/non-numeric `lat`/`lon` (geometry didn't parse).
- Off-island: outside PR latitude (17.80–18.60) or longitude (PR_LON_WEST..PR_LON_EAST).

MBIL-X is **distinct** from MBIL-0:
- `MBIL-0` = we scored, no built infrastructure within 15 km.
- `MBIL-X` = we couldn't score (no usable geometry or off-island context).

**MBIL-X never counts as corroborating** in `_assign_evidence_tier` and **never triggers** the `aasb_mbil_corridor_flag`.

### MBIL math (current)

`_score_mbil` aggregates these signals into a single `[0, 1]` score per candidate, then bucketizes into MBIL-0..MBIL-3 by the ranges above:

1. **Nearest-municipal-boundary distance** (closer → higher score).
2. **Hydro overlap** (water adjacency adds infra load).
3. **Utility overlap** (power/comm overlay adds load).
4. **Terrain context** (flat / valley / coastal lift the score; ridge / interior depress it).

The score is a weighted combination; the bucketization is hard-cutoff (not fuzzy). The boundaries above are the operational reference.

### Guardrail: "MBIL alone cannot escalate" (Task 27)

`readiness/spiderweb_intake.py::_assign_evidence_tier` enforces this rule: **if the only positive evidence for a candidate is MBIL** (no hydro overlap, no utility overlap, no corridor membership, no airport anchor), the candidate's `evidence_tier` stays at **T4** or **T3** regardless of how high `mbil_class` is. A high `MBIL-3` score on a candidate with zero corroborating evidence does **not** promote it to T2 or T1.

Rationale: MBIL is *spatial context*, not *operational signal*. An aircraft observed once over an MBIL-3 area is not high-confidence evidence of mission intent. Corroborating evidence (hydro/utility/corridor/airport) must be present to escalate.

Test reference: `tests/test_spiderweb_intake.py` includes a case asserting MBIL-only candidates never reach T1/T2.

---

## Evidence tiers

Set by [`readiness/spiderweb_intake.py::_assign_evidence_tier`](../readiness/spiderweb_intake.py).

| Tier | Operational meaning | Promotion gate |
|---|---|---|
| `T1` | Highest-confidence — confirmed identity + corroborating signals + airport anchor. | `confidence >= CONFIDENCE_T1 (0.65)` and ≥ 2 corroborating evidence types and airport-anchored |
| `T2` | Strong — multiple corroborating signals but missing one of the T1 gates. | `confidence >= CONFIDENCE_T2 (0.40)` and ≥ 2 corroborating evidence types |
| `T3` | Single-source — one signal type, plausible. | `confidence >= CONFIDENCE_REJECTED (0.25)` |
| `T4` | Lowest accepted — single source, low confidence; routed to manual review queue. | passes minimum acceptance but does not meet T3 |

Candidates below `CONFIDENCE_REJECTED` are dropped before tier assignment.

---

## Alias map (natural language → canonical)

For producers ingesting free-text logs / OCR captions, the canonical IDs below should be substituted in. Aliases are not exhaustive — the operational registry lives at [`configs/operator_aliases.yaml`](../configs/operator_aliases.yaml).

| Natural language | Canonical |
|---|---|
| "point of interest", "spot", "site", "location" | `POI` |
| "loiter pattern", "circling", "race-track pattern" | `ILAP` (when recurring) |
| "airport hop", "airport pair", "shuttle route" | `AASB` |
| "flight corridor", "route", "lane" | `corridor` |
| "river", "coastline", "shoreline", "harbor" | `hydro` |
| "power line", "antenna", "tower", "substation", "tank farm" | `utility` |
| "factory", "plant", "quarry", "warehouse cluster" | `industrial` |
| "town", "village", "city" | `municipal_boundary` (record distance, not name) |

For corridor names specifically, see [`configs/corridor_registry.yaml`](../configs/corridor_registry.yaml). The May 29 generated registry has `AASB-1` etc. as canonical corridor IDs with their flight counts and top POIs.

For mission types, see [`configs/mission_type_registry.yaml`](../configs/mission_type_registry.yaml).

For operator-name canonicalization (e.g., "Southwest Av" → "Southwest Aviation"), see [`configs/operator_aliases.yaml`](../configs/operator_aliases.yaml).

---

## Field-by-field meaning (`spiderweb_overlay_candidates.geojson` properties)

| Field | Type | Meaning | Producer |
|---|---|---|---|
| `source_layer` | string | Always `"airspace_spiderweb_export"` (provenance back to the producing layer). | `_normalize` |
| `candidate_type` | string | One of `poi`, `ilap`, `corridor`, `aasb_edge`. | inherited from input geojson |
| `lat`, `lon` | float | EPSG:4326 centroid (rounded to 6 dp = ~10 cm). | `_normalize` |
| `confidence` | float in `[0, 1]` | Per [Confidence-scale policy](SCHEMA_AND_EXPORT_CONTRACTS.md#confidence-scale-policy). | inherited from producer; clamped |
| `evidence_tier` | `T1`/`T2`/`T3`/`T4` | See [Evidence tiers](#evidence-tiers). | `_assign_evidence_tier` |
| `linked_flight_id` | string \| null | FK to a primary flight, when present. | `_normalize` from `props.flight_id` |
| `linked_aircraft` | string \| null | Aircraft callsign or registration (dominant if multiple). | `_normalize` |
| `corridor_id` | string \| null | Canonical corridor ID (see [`configs/corridor_registry.yaml`](../configs/corridor_registry.yaml)). | `_corridor_id` |
| `mbil_class` | `MBIL-0`..`MBIL-3` | See [MBIL classes](#mbil-maximum-built-infrastructure-load-classes). | `_score_mbil` |
| `hydro_overlap` | bool | True if candidate intersects a hydro reference. | `_score_hydro` |
| `utility_overlap` | bool | True if candidate intersects a utility reference. | `_score_utility` |
| `terrain_context` | string | Coarse terrain class (`flat`, `coastal`, `valley`, `ridge`, etc.). | `_score_terrain` |
| `review_status` | string | `unreviewed`/`reviewing`/`approved`/`rejected`. | manual review queue (downstream) |

The overlay also carries a top-level `summary` block with `bbox`, `centroid`, `feature_count`, `geometry_types`, `crs` — produced by `provenance_utils.feature_collection_summary()`.

---

## Cross-references

- [`schemas/spiderweb_observation.schema.json`](../schemas/spiderweb_observation.schema.json) — JSON Schema for individual observations.
- [`schemas/aasb_export.schema.json`](../schemas/aasb_export.schema.json) — Edge-CSV schema.
- [`schemas/ilap_corridor_candidate.schema.json`](../schemas/ilap_corridor_candidate.schema.json) — ILAP / corridor candidates.
- [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) — full per-artifact contract.
