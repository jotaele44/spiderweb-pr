#!/usr/bin/env python3
"""Build the Spiderweb Pin model: taxonomy + Master Pin Registry v1 (labels-only).

Re-expresses ``configs/layer_catalog.yaml`` under the canonical Pin hierarchy

    SPIDERWEB_PR -> visibility_class -> domain -> pin_group -> pin_class -> pin_layer -> pin

(visibility class stays the TOP folder per project decision; the Pin model nests beneath).
Emits two generated artifacts:

  configs/pin_taxonomy.yaml        — the nested folder tree, Pin terms, per-layer flag.
  configs/master_pin_registry.yaml — flat islandwide index, one row per Pin Layer.

This pass is labels-only: zero atomic pins are bound (``pins: []``); every Pin Layer is
status=planned. Each Pin Layer gets a lifecycle FLAG (WIRED/GHOST/PLANNED/DEPRECATED) and
the build FAILS on any ORPHAN — a backend-served or pipeline-emitted layer missing from the
taxonomy (OUTPUT_ZERO_ORPHAN_PIN_SCHEMA).

Usage:
    python3 scripts/build_pin_registry.py            # write both artifacts
    python3 scripts/build_pin_registry.py --dry-run  # audit only, write nothing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
PRODUCER = "scripts.build_pin_registry"
RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

CATALOG_PATH = REPO_ROOT / "configs" / "layer_catalog.yaml"
TAXONOMY_PATH = REPO_ROOT / "configs" / "pin_taxonomy.yaml"
REGISTRY_PATH = REPO_ROOT / "configs" / "master_pin_registry.yaml"
MANIFEST_PATH = REPO_ROOT / "data" / "_manifests" / "gis_layers_manifest.json"
BACKEND_MAIN = REPO_ROOT / "server" / "backend" / "main.py"

# ── layer_catalog `domain` slug -> Pin-model Domain (id, label) ────────────────
# The catalog tags each family with a fine-grained domain slug; the Pin model rolls
# them up into the highest thematic containers.
DOMAIN_ROLLUP: Dict[str, Tuple[str, str]] = {
    "admin": ("administrative", "Administrative"),
    "transportation": ("transportation_airspace", "Transportation & Airspace"),
    "lz": ("transportation_airspace", "Transportation & Airspace"),
    "aviation_facility": ("transportation_airspace", "Transportation & Airspace"),
    "flights": ("transportation_airspace", "Transportation & Airspace"),
    "corridor": ("transportation_airspace", "Transportation & Airspace"),
    "hydro": ("hydrology", "Hydrology"),
    "hydro_graph": ("hydrology", "Hydrology"),
    "subsurface": ("hydrology", "Hydrology"),
    "power": ("utilities", "Utilities"),
    "water_sewer": ("utilities", "Utilities"),
    "telecom": ("utilities", "Utilities"),
    "petroleum": ("utilities", "Utilities"),
    "utility": ("utilities", "Utilities"),
    "civic_social_infrastructure": ("institutional_civic", "Institutional & Civic"),
    "sites": ("public_safety_ops", "Public Safety & Operations"),
    "public_safety": ("public_safety_ops", "Public Safety & Operations"),
    "ilap": ("analytic_constructs", "Analytic Constructs"),
    "anomaly": ("analytic_constructs", "Analytic Constructs"),
}

# Names reserved with no producer yet -> PLANNED (vs GHOST = expected from pipeline).
PLANNED_LAYERS = {"airports", "hangar_candidates"}
# Explicit deprecations (none yet); kept for the lifecycle flag contract.
DEPRECATED_LAYERS: set = set()

ACRONYMS = {
    "Ilap": "ILAP", "Aasb": "AASB", "Lz": "LZ", "Nid": "NID", "Fic": "FIC",
    "Osap": "OSAP", "Poi": "POI", "Pr": "PR", "Pri": "PRI", "Uscg": "USCG",
}

# Pin Class derivation: trailing geometry / node-edge / version qualifiers describe a
# geometry or schema VARIANT of one Pin Class, so they collapse to a shared class.
_CLASS_SUFFIX = re.compile(r"_(point|polygon|line|nodes|edges)$")
_VERSION_SUFFIX = re.compile(r"_v\d+$")

_GEOM_BY_SUFFIX = [
    ("_polygon", "polygon"), ("_by_municipio", "polygon"),
    ("_line", "line"), ("_cable", "line"), ("pipeline", "line"), ("_edges", "line"),
    ("_point", "point"), ("_nodes", "point"),
]


def titleize(token: str) -> str:
    out = []
    for w in (w for w in re.split(r"[_\s]+", token) if w):
        cap = w.capitalize()
        out.append(ACRONYMS.get(cap, cap))
    return " ".join(out)


def class_id_for(layer_id: str) -> str:
    base = _VERSION_SUFFIX.sub("", layer_id)
    base = _CLASS_SUFFIX.sub("", base)
    return base or layer_id


def geometry_type_for(layer_id: str) -> str:
    low = layer_id.lower()
    for suffix, geom in _GEOM_BY_SUFFIX:
        if low.endswith(suffix) or (suffix == "pipeline" and low.startswith("pipeline")):
            return geom
    return "unknown"


def uid_prefix_for(domain_id: str, class_id: str) -> str:
    abbr = "".join(w[0] for w in domain_id.split("_"))[:3].upper() or "GEN"
    cls = re.sub(r"[^A-Z0-9]+", "", class_id.upper())[:10] or "PIN"
    return f"PIN_{abbr}_{cls}"


def load_emitted_layers() -> set:
    if not MANIFEST_PATH.exists():
        return set()
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {e["layer_id"] for e in data.get("layers", []) if e.get("layer_id")}


def load_backend_layers() -> set:
    if not BACKEND_MAIN.exists():
        return set()
    txt = BACKEND_MAIN.read_text(encoding="utf-8")
    m = re.search(r"_FALLBACK_LAYERS\s*=\s*\{(.*?)\}", txt, re.DOTALL)
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()


def flag_for(layer: Dict, emitted: set) -> str:
    lid = layer["layer_id"]
    if lid in DEPRECATED_LAYERS:
        return "DEPRECATED"
    if layer.get("pipeline_wired") or lid in emitted:
        return "WIRED"
    if lid in PLANNED_LAYERS:
        return "PLANNED"
    return "GHOST"


def build(catalog: Dict, emitted: set) -> Tuple[Dict, Dict, List[str]]:
    """Return (taxonomy, registry, layer_index) re-expressed in Pin terms."""
    vclasses = catalog["visibility_classes"]
    # tree[vclass][domain_id] = {label, pin_groups: {group_id: {...}}}
    tree: Dict[str, Dict] = {v: {} for v in vclasses}
    layer_index: List[Dict] = []
    flag_counts: Dict[str, int] = {}

    for fam in catalog["families"]:
        vclass = fam["visibility"]
        domain_id, domain_label = DOMAIN_ROLLUP.get(
            fam["domain"], (fam["domain"], titleize(fam["domain"])))
        domains = tree[vclass]
        if domain_id not in domains:
            domains[domain_id] = {"id": domain_id, "label": domain_label, "pin_groups": {}}
        groups = domains[domain_id]["pin_groups"]
        gid = fam["id"]
        if gid not in groups:
            groups[gid] = {"id": gid, "label": fam["label"], "pin_classes": {}}
        classes = groups[gid]["pin_classes"]

        for layer in fam["layers"]:
            lid = layer["layer_id"]
            cid = class_id_for(lid)
            if cid not in classes:
                classes[cid] = {"id": cid, "label": titleize(cid), "pin_layers": []}
            flag = flag_for(layer, emitted)
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
            geom = geometry_type_for(lid)
            uid_prefix = uid_prefix_for(domain_id, cid)
            classes[cid]["pin_layers"].append({
                "pin_layer": lid,
                "label": layer["label"],
                "geometry_type": geom,
                "flag": flag,
                "status": "planned",  # labels-only: no atomic pins bound yet
            })
            layer_index.append({
                "pin_uid_prefix": uid_prefix,
                "pin_layer": lid,
                "label": layer["label"],
                "visibility": vclass,
                "domain": domain_id,
                "pin_group": gid,
                "pin_class": cid,
                "geometry_type": geom,
                "flag": flag,
                "status": "planned",
                "evidence_tier": "T3",
                "review_flag": False,
            })

    # Materialize nested dict-of-dicts into ordered lists for stable YAML.
    vclass_blocks = []
    for vid, meta in vclasses.items():
        domains = tree.get(vid, {})
        if not domains:
            continue
        vclass_blocks.append({
            "visibility_class": vid,
            "label": meta["label"],
            "access_default": meta.get("access_default"),
            "domains": [
                {"id": d["id"], "label": d["label"], "pin_groups": [
                    {"id": g["id"], "label": g["label"], "pin_classes": [
                        {"id": c["id"], "label": c["label"], "pin_layers": c["pin_layers"]}
                        for c in grp_classes_sorted(g["pin_classes"])
                    ]}
                    for g in d["pin_groups"].values()
                ]}
                for d in domains.values()
            ],
        })

    taxonomy = {
        "version": "spiderweb_pin_taxonomy_v1",
        "generated_at": RUN_TS,
        "producer_module": PRODUCER,
        "binding": "labels_only",
        "root": "SPIDERWEB_PR",
        "hierarchy": ["visibility_class", "domain", "pin_group", "pin_class", "pin_layer", "pin"],
        "note": ("Pin-model re-expression of configs/layer_catalog.yaml. Visibility class is the "
                 "top folder; Domain -> Pin Group -> Pin Class -> Pin Layer nests beneath. No "
                 "atomic pins bound (labels-only)."),
        "flag_legend": {
            "WIRED": "Pipeline emits this Pin Layer.",
            "GHOST": "Catalogued, expected from pipeline, not yet emitted.",
            "PLANNED": "Reserved name, no producer yet.",
            "DEPRECATED": "Superseded; retained for lineage.",
        },
        "visibility_classes": vclass_blocks,
    }

    registry = {
        "version": "spiderweb_master_pin_registry_v1",
        "generated_at": RUN_TS,
        "producer_module": PRODUCER,
        "binding": "labels_only",
        "pin_record_schema": "schemas/pin.schema.json",
        "pin_link_schema": "schemas/pin_link.schema.json",
        "pin_count": 0,
        "layer_count": len(layer_index),
        "flag_summary": dict(sorted(flag_counts.items())),
        "note": ("Islandwide canonical Pin index. Zero atomic pins bound (labels-only) — "
                 "layer_index reserves the Domain/Pin Group/Pin Class/Pin Layer path and "
                 "pin_uid prefix for every layer; pins[] fills in a later pins-pass."),
        "layer_index": layer_index,
        "pins": [],
        "pin_links": [],
    }
    return taxonomy, registry, [li["pin_layer"] for li in layer_index]


def grp_classes_sorted(classes: Dict) -> List[Dict]:
    return list(classes.values())


def audit(catalogued: List[str], emitted: set, backend: set) -> int:
    catset = set(catalogued)
    dupes = sorted({l for l in catalogued if catalogued.count(l) > 1})
    orphan_backend = sorted(backend - catset)
    orphan_emitted = sorted(emitted - catset)
    ghosts = sorted(catset - emitted - backend) if emitted else []

    print(f"  pin layers mapped: {len(catalogued)}")
    print(f"  backend baseline: {len(backend)} ({len(orphan_backend)} orphaned)")
    print(f"  pipeline-emitted: {len(emitted) or 'manifest absent (orphan/ghost x-check skipped)'}")
    if dupes:
        print(f"  DUPLICATE pin_layer ids: {dupes}")
    if orphan_backend:
        print(f"  ORPHAN (backend-served, unmapped): {orphan_backend}")
    if orphan_emitted:
        print(f"  ORPHAN (pipeline-emitted, unmapped): {orphan_emitted}")
    if ghosts:
        print(f"  ghost (mapped, not yet emitted): {ghosts}")
    return len(dupes) + len(orphan_backend) + len(orphan_emitted)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="audit only; write nothing")
    args = ap.parse_args()

    import yaml
    from pipeline.config_loader import load_yaml_config

    catalog = load_yaml_config(
        CATALOG_PATH, required_keys=["version", "visibility_classes", "families"])
    emitted = load_emitted_layers()
    backend = load_backend_layers()

    taxonomy, registry, layer_ids = build(catalog, emitted)
    fatal = audit(layer_ids, emitted, backend)

    if args.dry_run:
        print("  (dry-run — no files written)")
    else:
        TAXONOMY_PATH.write_text(
            yaml.safe_dump(taxonomy, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8")
        REGISTRY_PATH.write_text(
            yaml.safe_dump(registry, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8")
        print(f"  wrote {TAXONOMY_PATH.relative_to(REPO_ROOT)}")
        print(f"  wrote {REGISTRY_PATH.relative_to(REPO_ROOT)}")

    if fatal:
        print(f"FAIL: {fatal} orphan/duplicate issue(s) — zero-orphan contract violated")
        return 1
    print("DONE — zero orphans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
