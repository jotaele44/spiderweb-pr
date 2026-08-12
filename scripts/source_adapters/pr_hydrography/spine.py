from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .control_plane import TransformContract, temporal_state_record, validate_transform
from .core import canonical_json, matching_text, sha256_bytes

ALLOWED_SOURCE_UNIVERSES = {
    "RESERVOIR_ENTITY_2004",
    "NID_DAM_ASSET",
    "POST_2004_CONSTRUCTED",
    "LEGACY_SMALL_HYDRO_IMPOUNDMENT",
    "USGS_BATHY_SURVEY_SUBJECT",
}

CLOSED_RELATIONSHIP_STATES = {
    "RELATIONSHIP_CONFIRMED_V4",
    "RELATIONSHIP_CONFIRMED_AUTHORITATIVE",
    "EXPECTED_ONTOLOGY_DIFFERENCE",
    "HISTORICAL_SEDIMENTED_OR_RETIRED",
    "NONRESERVOIR_STRUCTURE",
    "RESERVOIR_WITHOUT_NID_DAM",
    "DAM_WITHOUT_RESERVOIR_POLYGON",
}


def _entity_key(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("canonical_entity_id") or "").strip()
    if explicit:
        return explicit
    name = matching_text(row.get("canonical_name") or row.get("name") or row.get("source_name_raw"))
    if not name:
        raise RuntimeError("entity row lacks canonical_entity_id and usable name")
    return "NAME::" + name


def build_spine(rows: Iterable[Mapping[str, Any]], relationship_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    validate_transform(TransformContract("reservoir-spine", "RELATIONSHIP", "CANONICAL_ENTITY", "v0_1"))
    relationships = [dict(row) for row in relationship_rows]
    unresolved = [
        row for row in relationships
        if str(row.get("relationship_status") or row.get("state") or "") not in CLOSED_RELATIONSHIP_STATES
    ]
    if unresolved:
        ids = sorted(str(row.get("nid_id") or row.get("source_a_id") or "UNKNOWN") for row in unresolved)
        raise RuntimeError(f"cannot build canonical spine with unresolved relationship rows: {ids}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        universe = str(row.get("source_universe") or "")
        if universe not in ALLOWED_SOURCE_UNIVERSES:
            raise RuntimeError(f"unsupported source universe: {universe!r}")
        grouped[_entity_key(row)].append(row)

    entities = []
    for key in sorted(grouped):
        members = grouped[key]
        names = [str(row.get("canonical_name") or row.get("name") or row.get("source_name_raw") or "") for row in members]
        canonical_name = next((name for name in names if name), key)
        temporal = []
        for row in members:
            state = str(row.get("temporal_state") or "UNKNOWN")
            temporal.append(temporal_state_record(
                key,
                state,
                str(row.get("valid_from") or ""),
                str(row.get("valid_to") or ""),
                str(row.get("source_snapshot") or ""),
            ))
        entities.append({
            "canonical_entity_id": key,
            "canonical_name": canonical_name,
            "source_universes": sorted({str(row["source_universe"]) for row in members}),
            "source_names_raw": names,
            "nid_ids": sorted({str(row.get("nid_id")) for row in members if row.get("nid_id")}),
            "nhd_pids": sorted({str(row.get("nhd_pid")) for row in members if row.get("nhd_pid")}),
            "survey_dois": sorted({str(row.get("survey_doi")) for row in members if row.get("survey_doi")}),
            "temporal_states": temporal,
            "evidence_rows": len(members),
        })

    document = {
        "schema": "spiderweb.pr_hydrography.reservoir_entity_spine.v0_1",
        "canonical_identity_rule": "EXPLICIT_ID_OR_MATCHING_NAME_ONLY_FOR_PRE_ADJUDICATED_ROWS",
        "unresolved_relationship_rows": 0,
        "entity_count": len(entities),
        "entities": entities,
    }
    document["logical_fingerprint"] = sha256_bytes(canonical_json(document).encode("utf-8"))
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fail-closed longitudinal reservoir entity spine")
    parser.add_argument("--entities", required=True, help="JSON array of pre-adjudicated source-universe entity rows")
    parser.add_argument("--relationships", required=True, help="JSON array of closed relationship rows")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    rels = json.loads(Path(args.relationships).read_text(encoding="utf-8"))
    result = build_spine(rows, rels)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
