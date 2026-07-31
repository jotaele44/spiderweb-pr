#!/usr/bin/env python3
"""Gate OCR baseline runs on RLSM ontology readiness.

This script fails closed when required registry files are missing or common aliases fail resolution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from pipeline.normalize_locations import load_simple_yaml, normalize_location
from pipeline.normalize_missions import normalize_mission, normalize_blackout
from pipeline.normalize_operators import normalize_aircraft_identity, normalize_operator

ONTOLOGY_MANIFEST = "rlsm_operational_ontology.yaml"


def _required_registries(config_dir: Path) -> List[str]:
    """Read the required registry list from the ontology manifest.

    The manifest (configs/rlsm_operational_ontology.yaml) is the single source
    of truth for which registries the ontology layer depends on — hardcoding a
    second list here drifted when poi_registry was renamed to pin_registry and
    the corridor alias file split off from the observed-corridor catalog.
    """
    manifest = load_simple_yaml(config_dir / ONTOLOGY_MANIFEST)
    entries = manifest.get("required_registries", []) or []
    return [Path(str(entry)).name for entry in entries]


def run_gate(config_dir: Path = Path("configs")) -> Dict[str, object]:
    failures: List[str] = []
    warnings: List[str] = []

    if not (config_dir / ONTOLOGY_MANIFEST).exists():
        failures.append(f"missing ontology manifest: {ONTOLOGY_MANIFEST}")
        required = []
    else:
        required = _required_registries(config_dir)
        if not required:
            failures.append(f"ontology manifest lists no required_registries: {ONTOLOGY_MANIFEST}")
    for filename in required:
        if not (config_dir / filename).exists():
            failures.append(f"missing required config: {filename}")

    guardrail_path = config_dir / "location_naming_guardrails.yaml"
    if guardrail_path.exists():
        guardrails = load_simple_yaml(guardrail_path)
        principles = guardrails.get("principles", {}) or {}
        for required_rule in [
            "preserve_raw_label",
            "never_invent_site_names",
            "separate_visible_label_from_project_name",
            "require_review_for_unlabeled_locations",
        ]:
            if principles.get(required_rule) is not True:
                failures.append(f"location naming guardrail missing or false: {required_rule}")

    facility_operator_path = config_dir / "facility_operator_registry.yaml"
    if facility_operator_path.exists():
        facility_ops = load_simple_yaml(facility_operator_path)
        rules = facility_ops.get("rules", {}) or {}
        for required_rule in [
            "preserve_visible_operator_label",
            "preserve_unlabeled_operator_as_unresolved",
            "do_not_convert_context_operator_to_verified",
            "separate_facility_operator_from_aircraft_operator",
        ]:
            if rules.get(required_rule) is not True:
                failures.append(f"facility operator rule missing or false: {required_rule}")

    endpoint_audit_path = config_dir / "endpoint_recall_audit.yaml"
    if endpoint_audit_path.exists():
        endpoint_audit = load_simple_yaml(endpoint_audit_path)
        visual_cues = endpoint_audit.get("visual_track_cues", {}) or {}
        white_cue = visual_cues.get("WHITE_TRACK_LINE", {}) or {}
        if white_cue.get("allowed_endpoint_inference") != "endpoint_candidate_only":
            failures.append("white track line must be candidate-only")
        required_fields = endpoint_audit.get("required_audit_fields", []) or []
        for required_field in ["visual_track_color", "visual_track_cue"]:
            if required_field not in required_fields:
                failures.append(f"endpoint audit field missing: {required_field}")
        rules = endpoint_audit.get("matching_rules", {}) or {}
        for required_rule in [
            "preserve_visual_track_color",
            "audit_takeoff_and_landing_separately",
            "do_not_assume_white_track_line_confirms_takeoff_or_landing",
            "do_not_assume_track_start_equals_takeoff",
            "do_not_assume_track_end_equals_landing",
            "route_unlogged_endpoints_to_review",
            "create_project_location_id_for_new_unlogged_endpoint",
        ]:
            if rules.get(required_rule) is not True:
                failures.append(f"endpoint recall audit rule missing or false: {required_rule}")

    alias_expectations = {
        "SJU": {"resolved"},
        "TJSJ": {"resolved"},
        "Luis Munoz Marin": {"resolved"},
        # SIG is intentionally ambiguous since lz_registry v0_2: the Isla Grande
        # airport IATA and the lz_sig landing-zone point share the label.
        "SIG": {"resolved", "collision_review_required"},
        "Isla Grande": {"resolved"},
        "BQN": {"resolved"},
        # Ramey is intentionally ambiguous: airport, former-base complex, and Borinquen operational area.
        "Ramey": {"resolved", "collision_review_required"},
        "Vieques airport": {"resolved"},
    }
    for raw, expected_statuses in alias_expectations.items():
        resolved = normalize_location(raw, config_dir=config_dir)
        if resolved.get("resolution_status") not in expected_statuses:
            failures.append(f"alias resolution failed: {raw} -> {resolved}")

    for raw in ["N/A", "Unknown", "blocked"]:
        ident = normalize_aircraft_identity(raw)
        if ident.get("identity_status") != "masked_or_unresolved":
            failures.append(f"masked aircraft handling failed: {raw} -> {ident}")
        if ident.get("merge_policy") != "do_not_merge_without_cluster_evidence":
            failures.append(f"masked aircraft merge policy missing: {raw}")

    for raw in ["grid inspection", "coastal patrol", "private charter"]:
        mission = normalize_mission(raw, config_dir=config_dir)
        if mission.get("resolution_status") != "resolved":
            failures.append(f"mission alias failed: {raw} -> {mission}")

    operator = normalize_operator("USCG", config_dir=config_dir)
    if operator.get("resolution_status") != "resolved":
        failures.append(f"operator alias failed: USCG -> {operator}")

    # "track gap" resolves to the real UNKNOWN blackout class by design;
    # resolution_status distinguishes that from a failed lookup.
    blackout = normalize_blackout("track gap", config_dir=config_dir)
    if blackout.get("resolution_status") != "resolved":
        failures.append(f"blackout alias failed: track gap -> {blackout}")
    if not blackout.get("do_not_assume_intentional"):
        failures.append("blackout intent guard missing")

    status = "pass" if not failures else "fail"
    return {
        "gate": "rlsm_operational_ontology_v0_1",
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "ocr_baseline_allowed": status == "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default="configs")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()
    result = run_gate(Path(args.config_dir))
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
