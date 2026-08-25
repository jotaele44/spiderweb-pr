#!/usr/bin/env python3
"""Project spiderweb's evidence-envelope streams into PRII canonical streams.

spiderweb's native producer export is a domain envelope (events / observations /
tracks / sources with spiderweb_* schemas). This adapter re-projects those stream
files onto the Hub's canonical contract so the Hub can aggregate spiderweb
alongside the other producers:

  * each source record       -> one `sources` row + a `sensor_source` entity
    (or another entity_type, if the row's `kind` is a registered discriminator —
    see `_ENTITY_TYPE_BY_SOURCE_KIND`)
  * each event/observation/track -> one `entities` row (airspace_event/observation/track,
    or another entity_type per `_ENTITY_TYPE_BY_OBSERVATION_TYPE`)
  * each subject (aircraft callsign) -> one `entities` row (entity_type=aircraft)
  * record -[reported_by]-> source
  * record -[observed]-> aircraft  (when subject_id / callsign present)

Reads a package dir (defaults to exports/samples, accepting `<name>.jsonl` or
`<name>.sample.jsonl`) and writes `exports/federation/{sources,entities,
relationships}.jsonl` + a Hub-conformant manifest. Deterministic ids. Stdlib only.

NOTE (Z2): the canonical entity schema now carries an optional `location`
{lat, lon}; record entities (observations/events/tracks) project a representative
WGS84 point from their GeoJSON geometry/path so the query-hub's correlate_spatial
can join them against other producers' entities.

The export also carries a fourth stream, `observations`, produced by the PPP
geometry lane (see `build_ppp_geometry_streams`): moneysweep-pr federates a
concession project with a municipality and no coordinates, and this lane resolves
that municipality to a real point from a committed reference geography and hands
it back. The stream is omitted when no moneysweep-pr package is reachable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prii_export_utils import fid as _fid
from prii_export_utils import norm as _norm
from prii_export_utils import sha256 as _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
# Run as a script from anywhere: the PPP geometry lane imports from readiness/.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PRODUCER = "spiderweb-pr"
CONTRACT_VERSION = "1.0.0"
PRODUCER_SCRIPT = "scripts/federation_export.py"
STREAM_SCHEMA = {
    "sources": "federation_source.schema.json",
    "entities": "federation_entity.schema.json",
    "relationships": "federation_relationship.schema.json",
    "observations": "federation_observation.schema.json",
}
# Streams always written when non-empty, in package order. ``observations`` is
# the PPP geometry lane (see below) and is absent from packages built without a
# moneysweep-pr sibling checkout.
PACKAGE_STREAMS = ("sources", "entities", "relationships", "observations")
# spiderweb stream file -> canonical entity_type for its records
RECORD_STREAMS = {
    "airspace_events": "airspace_event",
    "observations": "airspace_observation",
    "tracks": "airspace_track",
}
# Per-row discriminators that override the stream-level default above (records)
# or the unconditional "sensor_source" default (sources), for newer non-airspace
# datasets projected onto the same envelope streams — see
# build_dataset_catalog_streams.py. Existing rows without a matching
# observation_type/kind fall through to the prior, unchanged behavior.
_ENTITY_TYPE_BY_OBSERVATION_TYPE = {"usgs_metallic_occurrence": "mineral_occurrence"}
_ENTITY_TYPE_BY_SOURCE_KIND = {"gis_layer_reference": "gis_layer_reference"}


def _score(conf: Any) -> float:
    if isinstance(conf, dict):
        return float(conf.get("score", 0.5))
    try:
        return float(conf)
    except (TypeError, ValueError):
        return 0.5


_ENVELOPE_INPUTS = ["exports/<package>/{sources,observations,airspace_events,tracks}.jsonl"]


def _lineage(
    phase: str,
    source_inputs: list[str] | None = None,
    extraction_method: str = "deterministic_envelope_projection",
) -> dict[str, Any]:
    return {
        "producer_script": PRODUCER_SCRIPT,
        "producer_phase": phase,
        "source_inputs": source_inputs or _ENVELOPE_INPUTS,
        "extraction_method": extraction_method,
    }


def _aircraft(record: dict[str, Any]) -> str | None:
    return record.get("subject_id") or (record.get("attributes") or {}).get("callsign")


def _point(record: dict[str, Any]) -> dict[str, float] | None:
    """Representative WGS84 {lat, lon} from a record's GeoJSON Point geometry or
    LineString path (first vertex). GeoJSON order is [lon, lat]. Returns None when
    absent or out of range (Z2)."""
    coords = None
    geom = record.get("geometry")
    if isinstance(geom, dict) and geom.get("type") == "Point":
        c = geom.get("coordinates")
        if isinstance(c, list) and len(c) >= 2:
            coords = c
    if coords is None:
        path = record.get("path")
        if isinstance(path, dict) and path.get("type") == "LineString":
            cc = path.get("coordinates")
            if isinstance(cc, list) and cc and isinstance(cc[0], list) and len(cc[0]) >= 2:
                coords = cc[0]
    if coords is None:
        return None
    lon, lat = coords[0], coords[1]
    if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return {"lat": round(float(lat), 6), "lon": round(float(lon), 6)}


def build_streams(sources_in: list[dict], records_by_stream: dict[str, list[dict]], now: str) -> dict[str, list[dict]]:
    sources: dict[str, dict] = {}
    src_entity: dict[str, str] = {}
    entities: dict[str, dict] = {}
    relationships: dict[str, dict] = {}

    for s in sources_in:
        raw = s.get("source_id") or s.get("id")
        synthetic = bool(s.get("is_synthetic"))
        score = _score(s.get("confidence"))
        sid = _fid("src", raw)
        sources[sid] = {
            "source_id": sid, "source_type": s.get("kind") or "unknown",
            "source_name": raw, "source_ref": raw, "confidence": score,
            "lineage": _lineage("SOURCE_REGISTRY"), "synthetic": synthetic,
            "created_at": s.get("first_seen_at") or now, "extracted_at": now,
        }
        ent_id = _fid("ent", "source", raw)
        src_entity[raw] = ent_id
        source_entity_type = _ENTITY_TYPE_BY_SOURCE_KIND.get(s.get("kind"), "sensor_source")
        entities[ent_id] = {
            "entity_id": ent_id, "source_id": sid, "name": raw,
            "normalized_name": _norm(raw), "entity_type": source_entity_type,
            "jurisdiction": "PR", "confidence": score, "lineage": _lineage("SOURCE_ENTITY"),
            "synthetic": synthetic, "created_at": s.get("first_seen_at") or now, "extracted_at": now,
        }

    for stream, etype in RECORD_STREAMS.items():
        for r in records_by_stream.get(stream, []):
            raw_src = r.get("source_id")
            sid = sources.get(_fid("src", raw_src), {}).get("source_id") or _fid("src", raw_src)
            synthetic = bool(r.get("is_synthetic"))
            score = _score(r.get("confidence"))
            when = r.get("observed_at") or r.get("event_time") or now
            rid = r.get("id")
            ent_id = _fid("ent", stream, rid)
            entity_type = _ENTITY_TYPE_BY_OBSERVATION_TYPE.get(r.get("observation_type"), etype)
            entities[ent_id] = {
                "entity_id": ent_id, "source_id": sid,
                "name": f"{entity_type} {rid[:8]}", "normalized_name": _norm(f"{entity_type} {rid[:8]}"),
                "entity_type": entity_type, "jurisdiction": "PR", "confidence": score,
                "lineage": _lineage("RECORD_ENTITY"), "synthetic": synthetic,
                "created_at": when, "extracted_at": now,
            }
            # Z2: project a representative point so correlate_spatial can join this
            loc = _point(r)
            if loc:
                entities[ent_id]["location"] = loc
            # reported_by -> source entity
            tgt = src_entity.get(raw_src) or _fid("ent", "source", raw_src)
            relationships.update(_rel(ent_id, "reported_by", tgt, sid, score, synthetic, when, now))
            # observed -> aircraft
            ac = _aircraft(r)
            if ac:
                ac_id = _fid("ent", "aircraft", _norm(ac))
                entities.setdefault(ac_id, {
                    "entity_id": ac_id, "source_id": sid, "name": ac,
                    "normalized_name": _norm(ac), "entity_type": "aircraft",
                    "jurisdiction": "PR", "confidence": score, "lineage": _lineage("AIRCRAFT_ENTITY"),
                    "synthetic": synthetic, "created_at": when, "extracted_at": now,
                })
                relationships.update(_rel(ent_id, "observed", ac_id, sid, score, synthetic, when, now))

    return {"sources": list(sources.values()),
            "entities": list(entities.values()),
            "relationships": list(relationships.values()),
            "observations": []}


# --------------------------------------------------------------------------
# PPP geometry lane
# --------------------------------------------------------------------------
# moneysweep-pr federates a PPP project with a municipality and no coordinates,
# by design: it owns the concession record, not the geography. This lane closes
# the loop — it resolves that municipality to a real point from spiderweb's
# committed reference geographies and hands the result back to the Hub.
#
# The result is emitted as an ``observations`` row rather than a location on
# moneysweep's entity, because a producer may only describe its own rows. The
# Hub's correlate_observations then joins the observation to every other
# producer's entity in the same municipality, which is how the point reaches the
# money project without either producer reaching into the other's data.
#
# Each observation is anchored to a spiderweb entity (the resolved asset
# location), because correlate_observations skips any observation whose anchor is
# not present in the aggregate.
PPP_SOURCE_REF = "spiderweb-pr:ppp_geometry"


def _ppp_lineage(phase: str, reference_path: str | None = None) -> dict[str, Any]:
    """Lineage for the PPP lane, which reads the producer package and a committed
    reference geography — not the envelope streams the rest of this script reads."""
    inputs = ["../moneysweep-pr/data/exports/canonical_v1_federation/entities.jsonl"]
    if reference_path:
        inputs.append(reference_path)
    return _lineage(phase, inputs, "reference_geography_resolution")


def build_ppp_geometry_streams(resolution: dict[str, Any], now: str) -> dict[str, list[dict]]:
    """Sources/entities/observations for resolved PPP concession geometry."""
    resolved = resolution.get("resolved") or []
    if not resolved:
        return {"sources": [], "entities": [], "observations": []}

    sid = _fid("src", PPP_SOURCE_REF)
    source = {
        "source_id": sid,
        "source_type": "reference_geography",
        "source_name": PPP_SOURCE_REF,
        "source_ref": PPP_SOURCE_REF,
        "confidence": 0.95,
        "lineage": _ppp_lineage("PPP_GEOMETRY"),
        "synthetic": False,
        "created_at": now,
        "extracted_at": now,
    }

    entities: list[dict] = []
    observations: list[dict] = []
    for row in resolved:
        name = f"{row['name']} (resolved location)"
        ent_id = _fid("ent", "ppp_asset_location", row["entity_id"])
        location = {
            "lat": row["lat"],
            "lon": row["lon"],
            "municipality": row["municipality"],
        }
        entities.append(
            {
                "entity_id": ent_id,
                "source_id": sid,
                "name": name,
                "normalized_name": _norm(name),
                "entity_type": "ppp_asset_location",
                "jurisdiction": "PR",
                "location": location,
                "confidence": row["geometry_confidence"],
                "lineage": _ppp_lineage(
                    "PPP_ASSET_LOCATION_ENTITY", row["reference_path"]
                ),
                "synthetic": False,
                "created_at": now,
                "extracted_at": now,
            }
        )
        observations.append(
            {
                "observation_id": _fid("obs", "ppp_geometry", row["entity_id"]),
                "source_id": sid,
                "entity_id": ent_id,
                "observation_type": "ppp_asset_location",
                "observed_at": now,
                "location": location,
                "attributes": {
                    # The producer row this geometry is for. The Hub joins on
                    # municipality, so this is provenance for a reviewer rather
                    # than a key — it records which money project was located,
                    # and by what.
                    "producer_entity_id": row["entity_id"],
                    "producer_project_name": row["name"],
                    "resolver": row["resolver"],
                    "reference_id": row["reference_id"],
                    "reference_path": row["reference_path"],
                    "producer_attribution_confidence": row.get(
                        "producer_attribution_confidence"
                    ),
                },
                "confidence": row["geometry_confidence"],
                "lineage": _ppp_lineage("PPP_GEOMETRY", row["reference_path"]),
                "synthetic": False,
                "created_at": now,
                "extracted_at": now,
            }
        )
    return {"sources": [source], "entities": entities, "observations": observations}


def merge_ppp_geometry(streams: dict[str, list[dict]], ppp: dict[str, list[dict]]) -> None:
    """Fold the PPP geometry lane into the canonical streams, in place."""
    known_sources = {s["source_id"] for s in streams["sources"]}
    for source in ppp["sources"]:
        if source["source_id"] not in known_sources:
            streams["sources"].append(source)
    known_entities = {e["entity_id"] for e in streams["entities"]}
    for entity in ppp["entities"]:
        if entity["entity_id"] not in known_entities:
            streams["entities"].append(entity)
    streams["observations"].extend(ppp["observations"])


def _rel(src_ent, rtype, tgt_ent, sid, score, synthetic, created, now):
    rid = _fid("rel", src_ent, rtype, tgt_ent)
    return {rid: {
        "relationship_id": rid, "source_id": sid, "source_entity_id": src_ent,
        "target_entity_id": tgt_ent, "relationship_type": rtype, "evidence_source_id": sid,
        "confidence": score, "lineage": _lineage("RELATIONSHIP"),
        "synthetic": synthetic, "created_at": created, "extracted_at": now,
    }}


# Primary-key field per canonical stream (used by the diff mode).
_ID_FIELD = {
    "sources": "source_id",
    "entities": "entity_id",
    "relationships": "relationship_id",
}


def _load_existing_streams(prev_dir: Path) -> dict[str, list[dict]]:
    """Load {sources,entities,relationships}.jsonl from a previous export dir."""
    out: dict[str, list[dict]] = {}
    for stream in ("sources", "entities", "relationships"):
        fp = prev_dir / f"{stream}.jsonl"
        out[stream] = (
            [json.loads(ln) for ln in fp.read_text().splitlines() if ln.strip()]
            if fp.exists() else []
        )
    return out


def diff_streams(new_streams: dict[str, list[dict]],
                 prev_streams: dict[str, list[dict]]) -> dict[str, Any]:
    """Per-stream added/removed/changed record diff keyed on the stream's id."""
    report: dict[str, Any] = {}
    for stream in ("sources", "entities", "relationships"):
        idf = _ID_FIELD[stream]
        new_by = {r[idf]: r for r in new_streams.get(stream, [])}
        old_by = {r[idf]: r for r in prev_streams.get(stream, [])}
        added = sorted(set(new_by) - set(old_by))
        removed = sorted(set(old_by) - set(new_by))
        changed = sorted(
            k for k in (set(new_by) & set(old_by))
            if json.dumps(new_by[k], sort_keys=True)
            != json.dumps(old_by[k], sort_keys=True)
        )
        report[stream] = {
            "added": len(added), "removed": len(removed), "changed": len(changed),
            "added_ids": added, "removed_ids": removed, "changed_ids": changed,
        }
    return report


def _read_stream(pkg: Path, name: str) -> list[dict]:
    for candidate in (pkg / f"{name}.jsonl", pkg / f"{name}.sample.jsonl"):
        if candidate.exists():
            return [json.loads(line) for line in candidate.read_text().splitlines() if line.strip()]
    return []


def write_package(streams, out_dir: Path, mode: str, now: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for stream in PACKAGE_STREAMS:
        rows = streams.get(stream) or []
        if not rows:
            continue
        fpath = out_dir / f"{stream}.jsonl"
        fpath.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        files.append({"filename": f"{stream}.jsonl", "stream": stream, "record_count": len(rows),
                      "sha256": _sha256(fpath), "schema_id": STREAM_SCHEMA[stream]})
    digest = hashlib.sha256(
        ("|".join(f"{f['filename']}:{f['sha256']}" for f in files) + f"|{mode}").encode()
    ).hexdigest()[:32]
    manifest = {"package_id": f"pkg_{digest}", "producer": PRODUCER,
                "export_contract_version": CONTRACT_VERSION, "mode": mode,
                "created_at": now, "extracted_at": now,
                "federation": {"producer_repo": PRODUCER, "hub_parent": "thehub-pr"},
                "files": files}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return out_dir / "manifest.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Project spiderweb envelope streams to PRII canonical streams.")
    ap.add_argument("--package", default=str(REPO_ROOT / "exports/samples"))
    ap.add_argument("--out", default=str(REPO_ROOT / "exports/federation"))
    ap.add_argument("--mode", default="test", choices=["test", "production"])
    ap.add_argument("--dry-run", action="store_true",
                    help="Build streams and report counts without writing any files.")
    ap.add_argument("--diff-from", default=None,
                    help="Compare the would-be export against a previous export dir.")
    ap.add_argument("--moneysweep-package", default=None,
                    help="moneysweep-pr canonical export dir to resolve PPP geometry from "
                         "(default: the sibling checkout). The lane is skipped when absent.")
    ap.add_argument("--no-ppp-geometry", action="store_true",
                    help="Skip the PPP geometry lane even if the producer package is present.")
    args = ap.parse_args()

    pkg = Path(args.package)
    sources_in = _read_stream(pkg, "sources")
    records = {name: _read_stream(pkg, name) for name in RECORD_STREAMS}
    if not sources_in and not any(records.values()):
        print(f"no envelope streams found in {pkg} — nothing to export")
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    streams = build_streams(sources_in, records, now)

    if not args.no_ppp_geometry:
        # Degrade gracefully: a checkout without the moneysweep-pr sibling still
        # produces a valid package, just without the PPP geometry lane.
        try:
            from readiness.ppp_geometry import resolve_projects

            resolution = resolve_projects(args.moneysweep_package)
        except Exception as exc:  # noqa: BLE001 - lane is optional, never fatal
            print(f"PPP geometry lane skipped: {exc}")
        else:
            merge_ppp_geometry(streams, build_ppp_geometry_streams(resolution, now))
            if resolution["unresolved_count"]:
                print(
                    f"PPP geometry: {resolution['resolved_count']} resolved, "
                    f"{resolution['unresolved_count']} left in the geocode queue"
                )

    if args.mode == "production":
        synthetic = [r for s in streams.values() for r in s if r.get("synthetic")]
        if synthetic:
            print(f"FAIL — {len(synthetic)} synthetic rows are not allowed in production mode")
            return 1

    counts = {k: len(v) for k, v in streams.items()}

    if args.diff_from:
        prev = _load_existing_streams(Path(args.diff_from))
        diff = diff_streams(streams, prev)
        print(json.dumps({"diff_from": args.diff_from, "diff": diff}, indent=2))

    if args.dry_run:
        print(json.dumps({"dry_run": True, "out": args.out, "counts": counts,
                          "would_write": [f"{s}.jsonl" for s, n in counts.items() if n]
                          + ["manifest.json"]}, indent=2))
        return 0

    manifest_path = write_package(streams, Path(args.out), args.mode, now)
    print(f"wrote {manifest_path} — {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
