#!/usr/bin/env python3
"""Build/audit the Spiderweb-PR Layer Catalog (labels & folder tree only — no pins).

Emits ``configs/layer_catalog.yaml``: a single source of truth that organizes every
map layer into a visibility-class → family → layer folder tree with canonical display
labels. This pass is *labels only* — no coordinates or geometry are bound; each layer
carries ``status: deferred``.

The editorial taxonomy (which family a layer belongs to, its visibility class) lives in
``FAMILY_PLAN`` below — that is the one place a human naming decision is made. Everything
else is *reconciled* against authoritative sources so a label is never invented twice or
a dataset left unnamed:

  - PRI.gpkg ``gpkg_contents``  → Public Infrastructure families (table names, verbatim)
  - server/backend/main.py      → ``_ALLOWED_LAYERS`` (every served layer must be catalogued)
  - data/_manifests/gis_layers_manifest.json (optional) → orphan/ghost audit when present

Audit output:
  - ORPHAN : discovered in a source but in no family  → would surface unlabeled. Fail-worthy.
  - GHOST  : catalogued but not discoverable in any source → stale name. Reported, not fatal
             (many analytic layers only exist after the pipeline runs).

Usage:
    python3 scripts/build_layer_catalog.py            # write configs/layer_catalog.yaml
    python3 scripts/build_layer_catalog.py --dry-run  # print audit only, write nothing
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER = "scripts.build_layer_catalog"
RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

CATALOG_PATH = REPO_ROOT / "configs" / "layer_catalog.yaml"
PRI_GPKG = REPO_ROOT / "data" / "sources" / "PRI.gpkg"
MANIFEST_PATH = REPO_ROOT / "data" / "_manifests" / "gis_layers_manifest.json"
BACKEND_MAIN = REPO_ROOT / "server" / "backend" / "main.py"

# ── Visibility ladder (top-level folders / the gate) ──────────────────────────
# V3 = freely shareable; V2 = restricted/operational; V1 = most sensitive/analytic.
# Semantics mirror configs/place_aliases.yaml (V3 public, V2 restricted) and
# configs/access_status_vocab.yaml (PUBLIC / RESTRICTED / OBSERVE_ONLY).
VISIBILITY_CLASSES = {
    "V3": {"label": "Public / Shareable", "rank": 3, "access_default": "PUBLIC"},
    "V2": {"label": "Restricted / Operational", "rank": 2, "access_default": "RESTRICTED"},
    "V1": {"label": "Sensitive / Analytic", "rank": 1, "access_default": "OBSERVE_ONLY"},
}

# ── Acronym fixups so titleize() never mangles a domain term ───────────────────
ACRONYMS = {
    "Pri": "PRI", "Ilap": "ILAP", "Aasb": "AASB", "Lz": "LZ", "Nid": "NID",
    "Fic": "FIC", "Osap": "OSAP", "Spm": "SPM", "Poi": "POI", "Pr": "PR",
    "Geojson": "GeoJSON", "V1": "v1", "V2": "v2", "V3": "v3", "V4": "v4",
    "V5": "v5", "V6": "v6", "Uscg": "USCG", "Prepa": "PREPA", "Nwi": "NWI",
    "Prvi": "PRVI", "Dem": "DEM",
}

# Per-layer label overrides where titleize() is not enough.
LABEL_OVERRIDES = {
    "civic_headstart_pr": "Head Start Service Locations",
    "missing_persons_by_municipio": "Missing Persons by Municipio",
    "consolidated_master_registry": "Consolidated Master POI Registry",
    "public_schools_all": "Public Schools (All)",
    "natural_features_hydro": "Natural Features - Hydro (GNIS)",
    "natural_features_terrain": "Natural Features - Terrain (GNIS)",
    "natural_features_coastal": "Natural Features - Coastal (GNIS)",
}


def titleize(layer_id: str) -> str:
    words = [w for w in re.split(r"[_\s]+", layer_id) if w]
    out = []
    for w in words:
        cap = w.capitalize()
        out.append(ACRONYMS.get(cap, cap))
    return " ".join(out)


def label_for(layer_id: str) -> str:
    return LABEL_OVERRIDES.get(layer_id, titleize(layer_id))


# ── PRI.gpkg raw tables already wired into scripts/populate_dataset_layers.py ──
# (gpkg_specs + reference_only registrations). Tables NOT in this set are uploaded
# but not yet emitted as gis_layers — flagged pipeline_wired=false for a later pins-pass.
WIRED_PRI_TABLES = {
    "power_plant", "power_substation_polygon", "power_line", "wastewater_plant",
    "water_treatment_plant", "pumping_station", "water_reservoir", "mast",
    "power_tower", "power_generator_polygon",  # registered reference_only
}

# How each PRI table prefix maps to a V3 infrastructure family.
PRI_FAMILY_BY_PREFIX = [
    ("power_", "power_grid", "Power Grid", "power"),
    ("telecom_", "telecom", "Telecom", "telecom"),
    ("petroleum_", "petroleum_pipeline", "Petroleum & Pipeline", "petroleum"),
    ("pipeline", "petroleum_pipeline", "Petroleum & Pipeline", "petroleum"),
    ("wastewater_", "water_sewer", "Water & Sewer", "water_sewer"),
    ("water_", "water_sewer", "Water & Sewer", "water_sewer"),
    ("pumping_", "water_sewer", "Water & Sewer", "water_sewer"),
    ("mast", "utility_other", "Utility / Other", "utility"),
]

# ── Editorial taxonomy: family → (visibility, domain, member layer_ids) ────────
# Ordered mundane → operational → theorized. PRI families are appended dynamically.
FAMILY_PLAN: List[Dict] = [
    # ----- V3: public / mundane -----
    {"id": "admin_geographies", "label": "Administrative Geographies", "visibility": "V3",
     "domain": "admin", "layers": ["municipios", "tracts", "places", "barrios"]},
    {"id": "airports", "label": "Airports & Aerodromes", "visibility": "V3",
     "domain": "transportation", "layers": ["airports"]},
    {"id": "hydrology", "label": "Hydrology", "visibility": "V3",
     "domain": "hydro", "layers": ["hydro_points_normalized", "hydro_master_v3", "nid_dams",
                                   "wetlands_nwi_prvi"]},
    {"id": "industrial", "label": "Industrial Sites", "visibility": "V3",
     "domain": "industrial", "layers": ["industrial_master"]},
    {"id": "reference_gazetteer", "label": "Reference / Gazetteer", "visibility": "V3",
     "domain": "reference", "layers": ["gazetteer_pr_domestic_names"]},
    {"id": "natural_features", "label": "Natural Features (GNIS)", "visibility": "V3",
     "domain": "reference", "layers": ["natural_features_hydro", "natural_features_terrain",
                                       "natural_features_coastal"]},
    # ----- V2: restricted / operational -----
    {"id": "civic_social", "label": "Civic / Social Infrastructure", "visibility": "V2",
     "domain": "civic_social_infrastructure", "layers": ["civic_headstart_pr",
                                                         "public_schools_all"]},
    {"id": "landing_zones", "label": "Landing Zones", "visibility": "V2",
     "domain": "lz", "layers": ["landing_zones_master"]},
    {"id": "hangars_ramps", "label": "Hangars & Ramps", "visibility": "V2",
     "domain": "aviation_facility", "layers": ["hangar_candidates"]},
    {"id": "operational_sites", "label": "Operational Sites", "visibility": "V2",
     "domain": "sites", "layers": ["sites", "fire_stations_consolidated"]},
    {"id": "flight_activity", "label": "Flight Activity", "visibility": "V2",
     "domain": "flights", "layers": ["flights"]},
    {"id": "military_aviation", "label": "Military & Aviation", "visibility": "V2",
     "domain": "military", "layers": ["military_aviation"]},
    {"id": "public_safety", "label": "Public Safety", "visibility": "V2",
     "domain": "public_safety", "layers": ["missing_persons_cases", "missing_persons_by_municipio"]},
    # ----- V1: sensitive / theorized ("eye lab" = ILAP, spiderweb) -----
    {"id": "ilap_constructs", "label": "ILAP — Infrastructure-Linked Access Points",
     "visibility": "V1", "domain": "ilap",
     "layers": ["ilap_master_nodes", "ilap_predictions", "ilap_dem_anomalies",
                "hydro_candidate_nodes",
                "water_signals", "fic_osap_final_set_v3", "fic_osap_candidates_v2",
                "fic_osap_ilap_links_v4", "fic_osap_ilap_paths_v6"]},
    {"id": "aasb_corridors", "label": "AASB — Aerial Anomaly Surveillance Bands / Corridors",
     "visibility": "V1", "domain": "corridor",
     "layers": ["aasb_corridor_nodes", "corridors", "corridor_index_v1",
                "subsurface_corridors_master"]},
    {"id": "spiderweb_graph", "label": "Spiderweb Hydro Graph", "visibility": "V1",
     "domain": "hydro_graph",
     "layers": ["spiderweb_graph_nodes_v5", "spiderweb_graph_edges_v5",
                "consolidated_master_registry"]},
    {"id": "subsurface_karst", "label": "Subsurface / Karst", "visibility": "V1",
     "domain": "subsurface",
     "layers": ["karst_subsurface_nodes_v2", "karst_subsurface_edges_v2"]},
    {"id": "signal_anomaly", "label": "Signal / Anomaly & Shadow", "visibility": "V1",
     "domain": "anomaly", "layers": ["anomalies", "heatmap"]},
]

# ── Pipeline-emitted derivatives of PRI/warehouse tables ──────────────────────
# populate_dataset_layers exports these under their own layer_ids (see
# data/_manifests/gis_layers_manifest.json); each rides along in the family of its
# source table so the manifest cross-check never finds an uncatalogued layer.
# Family metadata is spelled out because these families are normally built by the
# PRI.gpkg scan, which is skipped on a fresh checkout (the gpkg is not in git).
EMITTED_LAYER_PLAN: List[Dict] = [
    {"id": "power_grid", "label": "Power Grid", "visibility": "V3", "domain": "power",
     "layers": ["pri_power_generator_polygons", "pri_power_lines", "pri_power_plants",
                "pri_power_towers", "pri_substations",
                "prepa_transmission_lines_2014", "prepa_transmission_structures_2014"]},
    {"id": "water_sewer", "label": "Water & Sewer", "visibility": "V3", "domain": "water_sewer",
     "layers": ["pri_pumping_stations", "pri_wastewater_plants", "pri_water_reservoirs",
                "pri_water_treatment_plants", "waterworks_master_v1"]},
    {"id": "utility_other", "label": "Utility / Other", "visibility": "V3",
     "domain": "utility", "layers": ["pri_masts"]},
]


def read_pri_tables() -> List[str]:
    if not PRI_GPKG.exists():
        print(f"  WARN  {PRI_GPKG.relative_to(REPO_ROOT)} absent — PRI families skipped")
        return []
    con = sqlite3.connect(str(PRI_GPKG))
    try:
        rows = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features' ORDER BY table_name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def pri_families(tables: List[str]) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Group PRI raw tables into V3 infrastructure families (preserving order)."""
    by_id: Dict[str, Dict] = {}
    order: List[str] = []
    extra: Dict[str, Dict] = {}  # per-layer_id provenance (pri_table, pipeline_wired)
    for t in tables:
        fam_id = fam_label = domain = None
        for prefix, fid, flabel, dom in PRI_FAMILY_BY_PREFIX:
            if t.startswith(prefix):
                fam_id, fam_label, domain = fid, flabel, dom
                break
        if fam_id is None:
            fam_id, fam_label, domain = "utility_other", "Utility / Other", "utility"
        if fam_id not in by_id:
            by_id[fam_id] = {"id": fam_id, "label": fam_label, "visibility": "V3",
                             "domain": domain, "layers": []}
            order.append(fam_id)
        by_id[fam_id]["layers"].append(t)
        extra[t] = {"pri_table": True, "pipeline_wired": t in WIRED_PRI_TABLES}
    return [by_id[i] for i in order], extra


def read_allowed_layers() -> List[str]:
    """Parse the backend's canonical baseline (_FALLBACK_LAYERS literal) out of
    server/backend/main.py. The live _ALLOWED_LAYERS is now derived from this catalog,
    so the fallback set is the stable list of layers the geo API must keep serving."""
    if not BACKEND_MAIN.exists():
        return []
    txt = BACKEND_MAIN.read_text(encoding="utf-8")
    m = re.search(r"_FALLBACK_LAYERS\s*=\s*\{(.*?)\}", txt, re.DOTALL)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def read_manifest_layers() -> List[str]:
    if not MANIFEST_PATH.exists():
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return [e["layer_id"] for e in data.get("layers", []) if e.get("layer_id")]


def build_catalog() -> Tuple[Dict, Dict[str, Dict]]:
    pri_tables = read_pri_tables()
    pri_fams, pri_extra = pri_families(pri_tables)

    # Insert PRI infrastructure families right after hydrology (still within V3 block).
    families = list(FAMILY_PLAN)
    insert_at = next((i for i, f in enumerate(families) if f["id"] == "hydrology"), 0) + 1
    families[insert_at:insert_at] = pri_fams

    # Emitted derivatives join their source table's family; when the PRI scan was
    # skipped (gpkg absent) the family is created from the plan's own metadata.
    extra_layers = {p["id"]: list(p["layers"]) for p in EMITTED_LAYER_PLAN}
    existing_ids = {f["id"] for f in families}
    missing = [p for p in EMITTED_LAYER_PLAN if p["id"] not in existing_ids]
    families[insert_at:insert_at] = [
        {**p, "layers": []} for p in missing  # layers come from extra_layers below
    ]

    catalog_families = []
    for fam in families:
        layer_ids = list(fam["layers"]) + extra_layers.get(fam["id"], [])
        layers = []
        for lid in layer_ids:
            entry = {"layer_id": lid, "label": label_for(lid), "status": "deferred"}
            if lid in pri_extra:
                entry.update(pri_extra[lid])
            layers.append(entry)
        catalog_families.append({
            "id": fam["id"], "label": fam["label"], "visibility": fam["visibility"],
            "domain": fam["domain"], "layers": layers,
        })

    catalog = {
        "version": "rlsm_layer_catalog_v0_1",
        "generated_at": RUN_TS,
        "producer_module": PRODUCER,
        "binding": "labels_only",
        "note": ("Folder labels & visibility gate only — no geometry/coordinates bound. "
                 "Every layer carries status=deferred until a later pins-pass wires it."),
        "visibility_classes": VISIBILITY_CLASSES,
        "families": catalog_families,
    }
    return catalog, pri_extra


def audit(catalog: Dict) -> int:
    """Print orphan/ghost/duplicate audit. Return count of fatal issues."""
    catalogued: List[str] = []
    dupes: List[str] = []
    for fam in catalog["families"]:
        seen_labels = set()
        for layer in fam["layers"]:
            lid = layer["layer_id"]
            if lid in catalogued:
                dupes.append(lid)
            catalogued.append(lid)
            if layer["label"] in seen_labels:
                dupes.append(f"{fam['id']}:{layer['label']}")
            seen_labels.add(layer["label"])
    catset = set(catalogued)

    allowed = read_allowed_layers()
    manifest = read_manifest_layers()

    orphan_allowed = [l for l in allowed if l not in catset]
    orphan_manifest = [l for l in manifest if l not in catset]
    ghosts = [l for l in catset if manifest and l not in manifest and l not in allowed]

    print(f"  catalog: {len(catalogued)} layers across {len(catalog['families'])} families, "
          f"{len(VISIBILITY_CLASSES)} visibility classes")
    print(f"  backend baseline (_FALLBACK_LAYERS): {len(allowed)} ({len(orphan_allowed)} orphaned)")
    print(f"  manifest layers: {len(manifest) or 'absent (skip orphan/ghost cross-check)'}")
    if dupes:
        print(f"  DUPLICATE labels/ids: {sorted(set(dupes))}")
    if orphan_allowed:
        print(f"  ORPHAN (served by backend, not catalogued): {orphan_allowed}")
    if orphan_manifest:
        print(f"  ORPHAN (in manifest, not catalogued): {orphan_manifest}")
    if ghosts:
        print(f"  ghost (catalogued, not yet emitted by pipeline): {sorted(ghosts)}")
    fatal = len(dupes) + len(orphan_allowed) + len(orphan_manifest)
    return fatal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="audit only; write nothing")
    args = ap.parse_args()

    import yaml  # PyYAML, same dependency the rest of configs/ uses

    catalog, _ = build_catalog()
    fatal = audit(catalog)

    if args.dry_run:
        print("  (dry-run — configs/layer_catalog.yaml not written)")
    else:
        CATALOG_PATH.write_text(
            yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8")
        print(f"  wrote {CATALOG_PATH.relative_to(REPO_ROOT)}")

    if fatal:
        print(f"FAIL: {fatal} fatal catalog issue(s)")
        return 1
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
