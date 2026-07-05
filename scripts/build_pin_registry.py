#!/usr/bin/env python3
"""Build the Spiderweb Pin model: taxonomy + Master Pin Registry v1.

Re-expresses ``configs/layer_catalog.yaml`` under the canonical Pin hierarchy:

    SPIDERWEB_PR -> visibility_class -> domain -> pin_group -> pin_class -> pin_layer -> pin

The registry remains labels-only until an atomic pins-pass populates ``pins[]``. The distributed
ILAP cluster model is attached as schema/control metadata so future Pins can be assigned into
ILAP Area -> ILAP Cluster -> Subcomponent Node without treating any isolated Pin as proof.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
PRODUCER = "scripts.build_pin_registry"
RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

CATALOG_PATH = REPO_ROOT / "configs" / "layer_catalog.yaml"
TAXONOMY_PATH = REPO_ROOT / "configs" / "pin_taxonomy.yaml"
REGISTRY_PATH = REPO_ROOT / "configs" / "master_pin_registry.yaml"
ILAP_CLUSTER_MODEL_PATH = REPO_ROOT / "configs" / "ilap_cluster_model.yaml"
MANIFEST_PATH = REPO_ROOT / "data" / "_manifests" / "gis_layers_manifest.json"
BACKEND_MAIN = REPO_ROOT / "server" / "backend" / "main.py"

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
    "industrial": ("industrial", "Industrial"),
    "military": ("transportation_airspace", "Transportation & Airspace"),
    "reference": ("administrative", "Administrative"),
    "sites": ("public_safety_ops", "Public Safety & Operations"),
    "public_safety": ("public_safety_ops", "Public Safety & Operations"),
    "ilap": ("analytic_constructs", "Analytic Constructs"),
    "anomaly": ("analytic_constructs", "Analytic Constructs"),
}

PLANNED_LAYERS = {"airports", "hangar_candidates"}
DEPRECATED_LAYERS: set = set()

ACRONYMS = {
    "Ilap": "ILAP",
    "Aasb": "AASB",
    "Lz": "LZ",
    "Nid": "NID",
    "Fic": "FIC",
    "Osap": "OSAP",
    "Poi": "POI",
    "Pr": "PR",
    "Pri": "PRI",
    "Uscg": "USCG",
}

_CLASS_SUFFIX = re.compile(r"_(point|polygon|line|nodes|edges)$")
_VERSION_SUFFIX = re.compile(r"_v\d+$")
_GEOM_BY_SUFFIX = [
    ("_polygon", "polygon"),
    ("_by_municipio", "polygon"),
    ("_line", "line"),
    ("_cable", "line"),
    ("pipeline", "line"),
    ("_edges", "line"),
    ("_point", "point"),
    ("_nodes", "point"),
]


def titleize(token: str) -> str:
    words = []
    for word in (w for w in re.split(r"[_\s]+", token) if w):
        cap = word.capitalize()
        words.append(ACRONYMS.get(cap, cap))
    return " ".join(words)


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
    abbr = "".join(word[0] for word in domain_id.split("_"))[:3].upper() or "GEN"
    cls = re.sub(r"[^A-Z0-9]+", "", class_id.upper())[:10] or "PIN"
    return f"PIN_{abbr}_{cls}"


def load_emitted_layers() -> set:
    if not MANIFEST_PATH.exists():
        return set()
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["layer_id"] for entry in data.get("layers", []) if entry.get("layer_id")}


def load_backend_layers() -> set:
    if not BACKEND_MAIN.exists():
        return set()
    txt = BACKEND_MAIN.read_text(encoding="utf-8")
    match = re.search(r"_FALLBACK_LAYERS\s*=\s*\{(.*?)\}", txt, re.DOTALL)
    return set(re.findall(r'"([^"]+)"', match.group(1))) if match else set()


def load_ilap_cluster_model() -> Dict:
    if not ILAP_CLUSTER_MODEL_PATH.exists():
        return {}
    import yaml

    return yaml.safe_load(ILAP_CLUSTER_MODEL_PATH.read_text(encoding="utf-8")) or {}


def flag_for(layer: Dict, emitted: set) -> str:
    layer_id = layer["layer_id"]
    if layer_id in DEPRECATED_LAYERS:
        return "DEPRECATED"
    if layer.get("pipeline_wired") or layer_id in emitted:
        return "WIRED"
    if layer_id in PLANNED_LAYERS:
        return "PLANNED"
    return "GHOST"


def grp_classes_sorted(classes: Dict) -> List[Dict]:
    return list(classes.values())


def build(catalog: Dict, emitted: set) -> Tuple[Dict, Dict, List[str]]:
    """Return taxonomy, registry, and the mapped layer IDs."""
    vclasses = catalog["visibility_classes"]
    tree: Dict[str, Dict] = {v: {} for v in vclasses}
    layer_index: List[Dict] = []
    flag_counts: Dict[str, int] = {}

    for family in catalog["families"]:
        vclass = family["visibility"]
        domain_id, domain_label = DOMAIN_ROLLUP.get(
            family["domain"], (family["domain"], titleize(family["domain"]))
        )
        domains = tree[vclass]
        domains.setdefault(domain_id, {"id": domain_id, "label": domain_label, "pin_groups": {}})
        groups = domains[domain_id]["pin_groups"]
        group_id = family["id"]
        groups.setdefault(group_id, {"id": group_id, "label": family["label"], "pin_classes": {}})
        classes = groups[group_id]["pin_classes"]

        for layer in family["layers"]:
            layer_id = layer["layer_id"]
            class_id = class_id_for(layer_id)
            classes.setdefault(class_id, {"id": class_id, "label": titleize(class_id), "pin_layers": []})
            flag = flag_for(layer, emitted)
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
            geom = geometry_type_for(layer_id)
            uid_prefix = uid_prefix_for(domain_id, class_id)
            classes[class_id]["pin_layers"].append(
                {
                    "pin_layer": layer_id,
                    "label": layer["label"],
                    "geometry_type": geom,
                    "flag": flag,
                    "status": "planned",
                }
            )
            layer_index.append(
                {
                    "pin_uid_prefix": uid_prefix,
                    "pin_layer": layer_id,
                    "label": layer["label"],
                    "visibility": vclass,
                    "domain": domain_id,
                    "pin_group": group_id,
                    "pin_class": class_id,
                    "geometry_type": geom,
                    "flag": flag,
                    "status": "planned",
                    "evidence_tier": "T3",
                    "review_flag": False,
                    "ilap_area_id": None,
                    "ilap_cluster_id": None,
                    "node_role": None,
                    "system_function": None,
                    "cluster_coherence_score": None,
                    "contradiction_flags": [],
                }
            )

    vclass_blocks = []
    for visibility_id, meta in vclasses.items():
        domains = tree.get(visibility_id, {})
        if not domains:
            continue
        vclass_blocks.append(
            {
                "visibility_class": visibility_id,
                "label": meta["label"],
                "access_default": meta.get("access_default"),
                "domains": [
                    {
                        "id": domain["id"],
                        "label": domain["label"],
                        "pin_groups": [
                            {
                                "id": group["id"],
                                "label": group["label"],
                                "pin_classes": [
                                    {
                                        "id": pin_class["id"],
                                        "label": pin_class["label"],
                                        "pin_layers": pin_class["pin_layers"],
                                    }
                                    for pin_class in grp_classes_sorted(group["pin_classes"])
                                ],
                            }
                            for group in domain["pin_groups"].values()
                        ],
                    }
                    for domain in domains.values()
                ],
            }
        )

    taxonomy = {
        "version": "spiderweb_pin_taxonomy_v1",
        "generated_at": RUN_TS,
        "producer_module": PRODUCER,
        "binding": "labels_only",
        "root": "SPIDERWEB_PR",
        "hierarchy": ["visibility_class", "domain", "pin_group", "pin_class", "pin_layer", "pin"],
        "note": (
            "Pin-model re-expression of configs/layer_catalog.yaml. Visibility class is the top "
            "folder; Domain -> Pin Group -> Pin Class -> Pin Layer nests beneath. No atomic pins bound."
        ),
        "flag_legend": {
            "WIRED": "Pipeline emits this Pin Layer.",
            "GHOST": "Catalogued, expected from pipeline, not yet emitted.",
            "PLANNED": "Reserved name, no producer yet.",
            "DEPRECATED": "Superseded; retained for lineage.",
        },
        "visibility_classes": vclass_blocks,
    }

    ilap_model = load_ilap_cluster_model()
    registry = {
        "version": "spiderweb_master_pin_registry_v1",
        "generated_at": RUN_TS,
        "producer_module": PRODUCER,
        "binding": "labels_only",
        "pin_record_schema": "schemas/pin.schema.json",
        "pin_link_schema": "schemas/pin_link.schema.json",
        "ilap_cluster_schema": "schemas/ilap_cluster.schema.json",
        "ilap_cluster_model": "configs/ilap_cluster_model.yaml",
        "pin_count": 0,
        "layer_count": len(layer_index),
        "flag_summary": dict(sorted(flag_counts.items())),
        "note": (
            "Islandwide canonical Pin index. Zero atomic pins bound (labels-only) — layer_index "
            "reserves the Domain/Pin Group/Pin Class/Pin Layer path and pin_uid prefix for every layer; "
            "pins[] fills in a later pins-pass. Distributed ILAP cluster fields are nullable until rescore."
        ),
        "distributed_ilap_cluster_model": {
            "version": ilap_model.get("version", "ilap_distributed_cluster_model_v1"),
            "status": ilap_model.get("status", "schema_control"),
            "assignment_fields": ilap_model.get("required_assignment_fields", []),
            "outputs": ilap_model.get("outputs", {}),
        },
        "layer_index": layer_index,
        "pins": [],
        "pin_links": [],
        "ilap_clusters": [],
    }
    return taxonomy, registry, [row["pin_layer"] for row in layer_index]


def audit(catalogued: List[str], emitted: set, backend: set) -> int:
    catset = set(catalogued)
    dupes = sorted({layer_id for layer_id in catalogued if catalogued.count(layer_id) > 1})
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="audit only; write nothing")
    args = parser.parse_args()

    import yaml
    from pipeline.config_loader import load_yaml_config

    catalog = load_yaml_config(CATALOG_PATH, required_keys=["version", "visibility_classes", "families"])
    emitted = load_emitted_layers()
    backend = load_backend_layers()

    taxonomy, registry, layer_ids = build(catalog, emitted)
    fatal = audit(layer_ids, emitted, backend)

    if args.dry_run:
        print("  (dry-run — no files written)")
    else:
        TAXONOMY_PATH.write_text(
            yaml.safe_dump(taxonomy, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        REGISTRY_PATH.write_text(
            yaml.safe_dump(registry, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        print(f"  wrote {TAXONOMY_PATH.relative_to(REPO_ROOT)}")
        print(f"  wrote {REGISTRY_PATH.relative_to(REPO_ROOT)}")

    if fatal:
        print(f"FAIL: {fatal} orphan/duplicate issue(s) — zero-orphan contract violated")
        return 1
    print("DONE — zero orphans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
