#!/usr/bin/env python3
"""Validate the frozen PR archipelago evidence bridge without claiming certification."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "registry/spatial/pr_archipelago_evidence_bridge_v1_1.json"


def main() -> int:
    data = json.loads(BRIDGE.read_text(encoding="utf-8"))
    problems: list[str] = []
    if data.get("contract_version") != "federation-spatial-archipelago-evidence-bridge/1.1":
        problems.append("contract version mismatch")

    denominator = data.get("source_manifestation_denominator", {})
    source = denominator.get("source_manifestations")
    retained = denominator.get("retained")
    excluded = denominator.get("excluded")
    candidate = denominator.get("candidate")
    unresolved = denominator.get("unresolved")
    if not all(isinstance(v, int) and v >= 0 for v in (source, retained, excluded, candidate, unresolved)):
        problems.append("invalid denominator counts")
    elif source != retained + excluded + candidate + unresolved:
        problems.append("source denominator arithmetic does not close")
    if denominator.get("explained_total") != source:
        problems.append("explained_total mismatch")
    if denominator.get("unexplained_residue") != 0:
        problems.append("unexplained source residue must be zero")
    if denominator.get("state") != "PASS_SOURCE_PARTITION_ONLY":
        problems.append("source partition state must not claim canonical PASS")

    gnis = data.get("frozen_manifestations", {}).get("gnis_current_island_points", {})
    if gnis.get("source_manifestations") != 148 or gnis.get("stable_feature_ids") != 148:
        problems.append("GNIS current stable-ID denominator mismatch")
    if gnis.get("duplicate_feature_ids") != 0:
        problems.append("GNIS duplicate feature IDs must remain zero")

    sige = data.get("frozen_manifestations", {}).get("sige_insular_reference_points", {})
    if sige.get("source_manifestations") != sige.get("candidate_not_identity", 0) + sige.get("known_identity_unresolved", 0):
        problems.append("SIGE source identity partition does not close")
    if sige.get("canonical_promotions") != 0:
        problems.append("SIGE legacy candidates must not self-promote")

    census = data.get("frozen_manifestations", {}).get("census_2025_coastline", {})
    if census.get("canonical_promotions") != 0 or census.get("state") != "CANDIDATE_NOT_IDENTITY":
        problems.append("Census coastline must remain candidate-not-identity")

    noaa = data.get("frozen_manifestations", {}).get("noaa_current_project_geometry", {})
    if noaa.get("source_records_total") != noaa.get("candidate_archipelago_records", 0) + noaa.get("excluded_non_archipelago_or_project_boundary_records", 0):
        problems.append("NOAA current project record partition does not close")
    if noaa.get("canonical_promotions") != 0:
        problems.append("NOAA project geometries must not self-promote")

    audit = data.get("current_geometry_audit", {})
    if audit.get("gnis_source_ids") != audit.get("polygon_covered", 0) + audit.get("polygon_noncontained", 0):
        problems.append("GNIS polygon coverage partition does not close")
    if audit.get("polygon_noncontained") != audit.get("noncontained_within_1km_of_frozen_shoreline", 0) + audit.get("noncontained_gt_1km", 0):
        problems.append("GNIS shoreline distance partition does not close")
    if audit.get("noncontained_gt_1km") != audit.get("gt_1km_hard_morphology_adjudicated", 0) + audit.get("gt_1km_current_morphology_open", 0):
        problems.append("high-distance morphology partition does not close")
    if audit.get("proximity_identity_promotions") != 0:
        problems.append("proximity cannot promote identity")

    gates = data.get("canonical_gates", {})
    if gates.get("canonical_identity_denominator_closed") is not False:
        problems.append("canonical identity denominator must remain open")
    if gates.get("canonical_geometry_denominator_closed") is not False:
        problems.append("canonical geometry denominator must remain open")
    if gates.get("runtime_activation") != "BLOCKED":
        problems.append("runtime must remain blocked while canonical gates are open")
    if gates.get("CURRENT_PR_ARCHIPELAGO") != "OPEN" or gates.get("GEOMETRIC_CURRENT") != "OPEN":
        problems.append("bridge must remain non-certifying")

    if data.get("certification_state") != "NON_CERTIFYING":
        problems.append("bridge certification state must be NON_CERTIFYING")

    if problems:
        print("FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("PASS: frozen archipelago source evidence arithmetic preserved; canonical gates remain OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
