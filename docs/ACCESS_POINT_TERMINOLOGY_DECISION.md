# Decision record: names for the access-point registries

Status: adopted on this branch, 2026-11-15. Open questions for the repository
owners are listed at the end.

## Decision

Two new registries are added to this repository: **Inland Access Points**
(caves, sinkholes, mine workings, tunnels, shafts and other terrestrial or
inland-subsurface features) and **Off-Shore Access Points** (seafloor
depressions, underwater entrances, submarine springs, offshore engineered
structures). The proposal that introduced them called them "ILAP" and "OSAP".

Those two acronyms are **not** used as machine identifiers for the new
registries. They are used only in running text, to say what the proposal
called them. In code, schemas, file names, routes and stored records the
registries are:

| Registry | Namespace | Code | Feature identifier | Observation identifier |
|---|---|---|---|---|
| Inland Access Points | `access_point.inland` | `INAP` | `INAP-PR-000001` | `INAP-OBS-<16 hex>` |
| Off-Shore Access Points | `access_point.offshore` | `OFAP` | `OFAP-PR-000001` | `OFAP-OBS-<16 hex>` |

Shared record kinds use `APSRC-` (source), `APGEO-` (derived geometry) and
`APREL-` (relationship) followed by 16 hexadecimal characters. A feature
identifier is an opaque sequence number: it carries no place, name or class.

The rules are implemented in `spiderweb/access_points/namespaces.py` and
tested in `tests/test_access_points_core.py`.

## Why the acronyms could not be reused

"ILAP" already means eight different things in this repository, and a ninth in
a sibling repository. "OSAP" appears only as an unexplained token. Adding a new
meaning under the same letters would have made every existing label ambiguous.

| # | Existing meaning | Where it is declared | What carries it | Class |
|---|---|---|---|---|
| 1 | A recurring, notably indirect flight track ("Intra-Lateral Asymmetric Path") | `docs/SPIDERWEB_LANGUAGE_BRIDGE.md` | `integration/ilap_airspace_bridge.py`, the value `ilap` of `candidate_type`, corridor ids of the form `ILAP_<flight>` | FACT |
| 2 | "Infrastructure-linked access point", with the alias "inferred landing access point" | `configs/spiderweb_terms.yaml`, `configs/project_language_bridge.yaml` | Term key `ILAP`; no code reads either file | FACT |
| 3 | A group of nine catalogue layers | `configs/layer_catalog.yaml` | Family `ilap_constructs`, layer ids such as `ilap_master_nodes` | FACT |
| 4 | A node-type vocabulary and 103 named nodes | `configs/ilap_registry.yaml` | Node ids `SW-ALL-NNNNNNN`, fields `ilap_type`, `ilap_class` | FACT |
| 5 | An investigation grouping: ILAP Area and ILAP Cluster | `docs/ILAP_DISTRIBUTED_CLUSTER_SYSTEM.md`, `configs/ilap_cluster_model.yaml` | Ids `ILAP_AREA_*`, `ILAP_CLUSTER_*`; `schemas/ilap_cluster.schema.json` | FACT |
| 6 | A terrain screening score | `tools/pr_dem_one_tile_pilot.py` | Column `ILAP_SCORE` | FACT |
| 7 | A rail source dataset ("Ferrocarril ILAP Master") | `configs/ferrocarril_source.yaml` | Ids `FERRO-NNNN`, layer `ferrocarril_ilap_candidates` | FACT |
| 8 | An enrichment hook | `spiderweb/enrichment/headstart_context_enricher.py` | Field `ilap_context_distance_m` | FACT |
| 9 | "Infrastructure-Linked Airspace Point", with governed threshold ids `ILAP-WEIGHT-*`, `ILAP-GRID-0.05DEG` and others | skywatcher-pr vocabulary registries | Sibling repository | FACT |

"OSAP" and "FIC" are never expanded anywhere in the repository. They appear in
four catalogue layer ids (`fic_osap_final_set_v3`, `fic_osap_candidates_v2`,
`fic_osap_ilap_links_v4`, `fic_osap_ilap_paths_v6`) whose source files are
operator-local and are not in the repository, and in link-type values such as
`OSAP_to_ILAP`. Whether "OSAP" in those files already meant an off-shore access
point cannot be established from the repository. [UNKNOWN]

Three existing generators also assign behaviour by substring, so a new layer
id containing the old tokens would silently inherit it:
`scripts/populate_dataset_layers.py` assigns the manifest domain `ilap` to any
layer id containing that substring and switches off the land bounding-box
filter for ids starting `fic_osap`; `scripts/build_layer_catalog.py` and
`scripts/build_pin_registry.py` rewrite the tokens `ilap`, `osap` and `fic`
into upper-case acronyms in labels. [FACT]

## What the decision does

1. **Every meaning has its own namespace.** `classify_identifier` maps each
   existing spelling to the namespace it has always had:
   `aviation.ilap_path`, `investigation.ilap_area`,
   `investigation.ilap_cluster`, `analytic.ilap_infrastructure_linked`,
   `source.fic_osap`, `terrain.ilap_score`, `source.ferrocarril_ilap`,
   `enrichment.ilap_context`. None of them is a registry namespace.
2. **Nothing is equal across namespaces.** An identifier is only meaningful
   with its namespace. Two records with the same spelling in different
   namespaces are different things, and code that tries to merge, match or
   deduplicate across namespaces raises an error.
3. **A bare acronym is refused.** Asking what `ILAP` or `OSAP` means on its
   own raises an error, because guessing is the failure this decision exists
   to prevent.
4. **New identifiers never contain the old tokens.** `ilap`, `osap`, `fic`
   and `aasb` are reserved. `validate_new_machine_identifier` rejects them; a
   test applies it to every module, schema, registry file and enum value in
   the new package.
5. **Nothing existing is renamed, migrated or edited.** The aviation bridge,
   the cluster schemas, the catalogue layers and the legacy node registry are
   untouched. Layer labels feed hashed identifiers that the federation hub
   already holds, so renaming them would also change those identifiers.

## Provisional labels

The proposal named five initial off-shore candidates `OSAP-SEED-001` to
`OSAP-SEED-005`. These are kept exactly as given, as **raw source labels**.
A label is not an identity: the registry assigns each record its own
`OFAP-PR-` identifier, and code that tries to use a label as a feature
identifier fails.

## What was tested against the proposal

The proposal suggested the namespaces `access.inland`, `access.offshore`,
`aviation.ilap_path` and `investigation.ilap_cluster`. Two changes were made:

- `access.*` became `access_point.*`. In this repository "access" already
  means entitlement (`access_class`, `access_default`, `access_method`), and
  "inland" and "offshore" are already terrain-context values
  (`pipeline/terrain_hook.py`). `access_point.inland` reads as a registry name
  rather than as either of those.
- Five namespaces were added for meanings the proposal did not list (rows 2,
  3–4, 6, 7 and 8 above, and the `FIC_OSAP` layers).

## Consequences

- Anyone searching the code for "ILAP" will not find the new registries. This
  document, the disambiguation table in `docs/SPIDERWEB_LANGUAGE_BRIDGE.md`
  and the `INAP` / `OFAP` entries in `configs/project_language_bridge.yaml`
  are the bridge.
- Existing tests, exports and consumers of the older meanings are unaffected.
- The legacy node registry is read through an explicit crosswalk
  (`configs/access_point_legacy_crosswalk.yaml`) that turns five of its 103
  nodes into candidate records. The legacy file itself is never modified.

## Open questions for the owners

1. **Who owns the canonical definition of ILAP?** skywatcher-pr declares
   "Infrastructure-Linked Airspace Point" canonical and lists this
   repository's two expansions as a historical alias and a prohibited
   inference alias. The two repositories disagree. [OPEN]
2. **What do FIC and OSAP expand to in the operator's source datasets?** If
   OSAP there already means off-shore access point, the new registry
   continues that work and the `FIC_OSAP` layers should be crosswalked into
   it; that needs the source files, which are not in the repository. [OPEN]
3. **Should the alias "inferred landing access point" remain?** It asserts an
   inference in its own name and the sibling repository prohibits it. [OPEN]
