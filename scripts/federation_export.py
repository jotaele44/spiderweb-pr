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
relationships}.jsonl` + a Hub-conformant manifest. Deterministic ids. Besides the
pinned prii-export-utils package, stdlib only; the source_monitors stream below
also reads a YAML registry, which needs PyYAML (the `airspace` extra).

NOTE (Z2): the canonical entity schema now carries an optional `location`
{lat, lon}; record entities (observations/events/tracks) project a representative
WGS84 point from their GeoJSON geometry/path so the query-hub's correlate_spatial
can join them against other producers' entities.

The export also carries a fourth stream, `observations`, produced by the PPP
geometry lane (see `build_ppp_geometry_streams`): moneysweep-pr federates a
concession project with a municipality and no coordinates, and this lane resolves
that municipality to a real point from a committed reference geography and hands
it back. The stream is omitted unless an explicit verified moneysweep-pr package
is supplied.

A fifth lane, the site imagery timeline (`build_site_imagery_streams`), adds a
`site_imagery_series` entity per registered site plus provisional `satellite_scene`
and `satellite_visible_change` observations. It is omitted unless a timeline document
is passed with `--site-imagery-timeline`, and an invalid document fails the export
instead of being skipped.

Every package also carries `source_monitors` (thehub-pr ADR 0013, see
`build_source_monitors`): one row per source this repo's registries say it
monitors, with when the source last succeeded and how that is known.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prii_export_utils import SourceRunState, resolve_last_success, source_monitor_row
from prii_export_utils import fid as _fid
from prii_export_utils import norm as _norm
from prii_export_utils import sha256 as _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
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
    "source_monitors": "federation_source_monitor.schema.json",
}
PACKAGE_STREAMS = (
    "sources", "entities", "relationships", "observations", "source_monitors",
)
RECORD_STREAMS = {
    "airspace_events": "airspace_event",
    "observations": "airspace_observation",
    "tracks": "airspace_track",
}
_ENTITY_TYPE_BY_OBSERVATION_TYPE = {"usgs_metallic_occurrence": "mineral_occurrence"}
_ENTITY_TYPE_BY_SOURCE_KIND = {"gis_layer_reference": "gis_layer_reference"}


# Additive FEDERATION_EPISTEMIC_STATE_CONTRACT_V1 declarations (thehub-pr,
# candidate; vendored at schemas/federation_epistemic_state.v1.schema.json).
# Only record types whose provenance is documented get a class/geometry claim;
# anything else is left undeclared so the Hub fails closed (UNCLASSIFIED/UNKNOWN).
EVIDENCE_STATE_CONTRACT = "federation-evidence-state-v1"
# observation_type -> (epistemic_class, geometry_precision, coordinate_method, observation_state)
_RECORD_EVIDENCE: dict[str, tuple[str, str, str, str | None]] = {
    # USGS OFR 98-038 metallic *point* coverage: LAB coordinates are the
    # published occurrence points (data/usgs_ofr_98_038/docs).
    "usgs_metallic_occurrence": ("CURATED", "OBSERVED_POINT", "AUTHORITATIVE", "OBSERVED_PRESENT"),
    # Airport reference points: an official point standing in for the airfield.
    "airport_reference_location": ("CURATED", "REPRESENTATIVE_POINT", "AUTHORITATIVE", None),
    # Operator-placed point on imagery after human review (visual only).
    "structure_sighting": ("CURATED", "INTERPRETED_POINT", "INFERRED", "OBSERVED_PRESENT"),
}


def _evidence_state(**fields: Any) -> dict[str, Any]:
    declared = {k: v for k, v in fields.items() if v is not None}
    return {"contract": EVIDENCE_STATE_CONTRACT, "data_stage": "CANONICAL", **declared}


def _record_evidence_state(record: dict[str, Any], has_point: bool) -> dict[str, Any]:
    """Declaration for a record-derived row. A LineString's first vertex is
    only ever a representative point, whatever the record type."""
    spec = _RECORD_EVIDENCE.get(record.get("observation_type"))
    klass, precision, method, observation = spec if spec else (None, None, None, None)
    geom = record.get("geometry")
    from_point = isinstance(geom, dict) and geom.get("type") == "Point"
    if has_point and not from_point:
        precision, method = "REPRESENTATIVE_POINT", "FIRST_VERTEX"
    if not has_point:
        precision = method = None
    return _evidence_state(epistemic_class=klass, geometry_precision=precision,
                           coordinate_method=method, observation_state=observation)


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


# Record types whose subject_id names a non-aircraft subject (an airport, a
# site, a mineral occurrence). Their subjects must never become aircraft.
_NON_AIRCRAFT_SUBJECT_TYPES = frozenset(
    {"usgs_metallic_occurrence", "airport_reference_location", "structure_sighting"}
)


def _aircraft(record: dict[str, Any]) -> str | None:
    if record.get("observation_type") in _NON_AIRCRAFT_SUBJECT_TYPES:
        return None
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
            "evidence_state": _evidence_state(epistemic_class="CURATED"),
        }
        ent_id = _fid("ent", "source", raw)
        src_entity[raw] = ent_id
        source_entity_type = _ENTITY_TYPE_BY_SOURCE_KIND.get(s.get("kind"), "sensor_source")
        entities[ent_id] = {
            "entity_id": ent_id, "source_id": sid, "name": raw,
            "normalized_name": _norm(raw), "entity_type": source_entity_type,
            "jurisdiction": "PR", "confidence": score, "lineage": _lineage("SOURCE_ENTITY"),
            "synthetic": synthetic, "created_at": s.get("first_seen_at") or now, "extracted_at": now,
            "evidence_state": _evidence_state(epistemic_class="CURATED"),
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
            # Z2: project a representative point from source geometry into the canonical entity.
            loc = _point(r)
            if loc:
                entities[ent_id]["location"] = loc
            entities[ent_id]["evidence_state"] = _record_evidence_state(r, has_point=bool(loc))
            tgt = src_entity.get(raw_src) or _fid("ent", "source", raw_src)
            relationships.update(_rel(ent_id, "reported_by", tgt, sid, score, synthetic, when, now))
            ac = _aircraft(r)
            if ac:
                ac_id = _fid("ent", "aircraft", _norm(ac))
                entities.setdefault(ac_id, {
                    "entity_id": ac_id, "source_id": sid, "name": ac,
                    "normalized_name": _norm(ac), "entity_type": "aircraft",
                    "jurisdiction": "PR", "confidence": score, "lineage": _lineage("AIRCRAFT_ENTITY"),
                    "synthetic": synthetic, "created_at": when, "extracted_at": now,
                    # Keyed on a callsign/subject id: a callsign is not an airframe identity.
                    "evidence_state": _evidence_state(identity_state="CANDIDATE"),
                })
                relationships.update(_rel(ent_id, "observed", ac_id, sid, score, synthetic, when, now))

    return {"sources": list(sources.values()),
            "entities": list(entities.values()),
            "relationships": list(relationships.values()),
            "observations": []}


# --------------------------------------------------------------------------
# PPP geometry lane
# --------------------------------------------------------------------------
PPP_SOURCE_REF = "spiderweb-pr:ppp_geometry"


def _ppp_lineage(
    phase: str,
    resolution: dict[str, Any],
    reference_path: str | None = None,
) -> dict[str, Any]:
    """Content-addressed lineage for the verified upstream Moneysweep package."""
    package = resolution.get("producer_package") or {}
    inputs = [
        f"moneysweep-pr:package_id:{package.get('package_id')}",
        f"moneysweep-pr:manifest:sha256:{package.get('manifest_sha256')}",
        f"moneysweep-pr:{package.get('entities_filename')}:sha256:{package.get('entities_sha256')}",
    ]
    if reference_path:
        inputs.append(reference_path)
    lineage = _lineage(phase, inputs, "reference_geography_resolution")
    lineage["upstream_package"] = {
        "producer": package.get("producer"),
        "package_id": package.get("package_id"),
        "manifest_sha256": package.get("manifest_sha256"),
        "entities_filename": package.get("entities_filename"),
        "entities_sha256": package.get("entities_sha256"),
        "entities_record_count": package.get("entities_record_count"),
    }
    return lineage


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
        "lineage": _ppp_lineage("PPP_GEOMETRY", resolution),
        "synthetic": False,
        "created_at": now,
        "extracted_at": now,
        "evidence_state": _evidence_state(epistemic_class="CURATED"),
    }
    # A municipality resolved to a committed reference asset point: computed,
    # and only ever a representative point for the project's location.
    ppp_state = _evidence_state(epistemic_class="COMPUTED", geometry_precision="REPRESENTATIVE_POINT",
                                coordinate_method="LINKED_ASSET")

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
        lineage = _ppp_lineage(
            "PPP_ASSET_LOCATION_ENTITY", resolution, row["reference_path"]
        )
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
                "lineage": lineage,
                "evidence_state": dict(ppp_state),
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
                    "producer_entity_id": row["entity_id"],
                    "producer_project_name": row["name"],
                    "resolver": row["resolver"],
                    "reference_id": row["reference_id"],
                    "reference_path": row["reference_path"],
                    "producer_attribution_confidence": row.get("producer_attribution_confidence"),
                    "producer_package_id": row.get("producer_package_id"),
                    "producer_manifest_sha256": row.get("producer_manifest_sha256"),
                    "producer_entities_sha256": row.get("producer_entities_sha256"),
                    "producer_entities_record_count": row.get("producer_entities_record_count"),
                },
                "confidence": row["geometry_confidence"],
                "lineage": _ppp_lineage("PPP_GEOMETRY", resolution, row["reference_path"]),
                "evidence_state": dict(ppp_state),
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


# --------------------------------------------------------------------------
# Site imagery timeline lane (spiderweb/site_timeline, docs/contracts/
# SITE_IMAGERY_TIMELINE.md). Mirrors the PPP lane: a spiderweb-owned entity per
# registered site plus `observations` rows that point at it and carry the
# registering producer's entity id in attributes.producer_entity_id. The hub
# adjudicates any equivalence with that producer's entity (hub ADR 0009); this
# lane never claims it. Every row is provisional. Omitted unless a timeline
# document is passed with --site-imagery-timeline.
# --------------------------------------------------------------------------
SITE_IMAGERY_SOURCE_REF = "spiderweb-pr:site_imagery_timeline"
# Confidence ceilings for this lane. They duplicate PRECISE_CONFIDENCE_CAP and
# COARSE_CONFIDENCE_CAP in spiderweb.site_timeline.models (uncalibrated heuristics) so
# this script's default import surface stays unchanged; a test pins them together.
SITE_IMAGERY_SOURCE_CONFIDENCE = 0.6
SITE_IMAGERY_COARSE_CONFIDENCE = 0.3


def _site_imagery_lineage(
    phase: str, doc_sha256: str, document: dict[str, Any]
) -> dict[str, Any]:
    window = document.get("window") or {}
    lineage = _lineage(
        phase,
        [f"site_imagery_timeline:sha256:{doc_sha256}"],
        "provisional_visible_change_projection",
    )
    lineage["upstream_document"] = {
        "schema_version": document.get("schema_version"),
        "sha256": doc_sha256,
        "adapter": document.get("adapter"),
        "window_start": window.get("start"),
        "window_end": window.get("end"),
    }
    return lineage


def build_site_imagery_streams(
    document: dict[str, Any], now: str
) -> dict[str, list[dict]]:
    """Sources/entities/observations for a validated site imagery timeline document."""
    sites = document.get("sites") or []
    if not sites:
        return {"sources": [], "entities": [], "observations": []}

    doc_sha = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    synthetic = bool(document.get("synthetic"))
    sid = _fid("src", SITE_IMAGERY_SOURCE_REF)
    source = {
        "source_id": sid,
        "source_type": "satellite_imagery_timeline",
        "source_name": SITE_IMAGERY_SOURCE_REF,
        "source_ref": SITE_IMAGERY_SOURCE_REF,
        "confidence": SITE_IMAGERY_SOURCE_CONFIDENCE,
        "lineage": _site_imagery_lineage("SITE_IMAGERY_SOURCE", doc_sha, document),
        "synthetic": synthetic,
        "created_at": now,
        "extracted_at": now,
        "evidence_state": _evidence_state(epistemic_class="COMPUTED"),
    }
    # A scene row is a provider catalog fact (CURATED); a change row is a computed
    # difference (COMPUTED). Both place the site at its registry point, which is only
    # ever a representative point for the site chip.
    scene_state = _evidence_state(
        epistemic_class="CURATED",
        geometry_precision="REPRESENTATIVE_POINT",
        coordinate_method="REGISTRY_SITE_POINT",
    )
    change_state = _evidence_state(
        epistemic_class="COMPUTED",
        geometry_precision="REPRESENTATIVE_POINT",
        coordinate_method="REGISTRY_SITE_POINT",
    )

    entities: list[dict] = []
    observations: list[dict] = []
    for entry in sites:
        site = entry["site"]
        producer_ent = site["producer_entity_id"]
        name = f"{site['name']} (imagery series)"
        ent_id = _fid("ent", "site_imagery_series", producer_ent)
        location = {"lat": site["lat"], "lon": site["lon"]}
        cap = (
            SITE_IMAGERY_COARSE_CONFIDENCE
            if site["geometry_coarse"]
            else SITE_IMAGERY_SOURCE_CONFIDENCE
        )
        common = {
            "producer_entity_id": producer_ent,
            "external_site_id": site["external_site_id"],
            "geometry_coarse": site["geometry_coarse"],
            "provisional": True,
        }
        entities.append(
            {
                "entity_id": ent_id,
                "source_id": sid,
                "name": name,
                "normalized_name": _norm(name),
                "entity_type": "site_imagery_series",
                "jurisdiction": "PR",
                "location": location,
                "confidence": cap,
                "lineage": _site_imagery_lineage(
                    "SITE_IMAGERY_SERIES_ENTITY", doc_sha, document
                ),
                "evidence_state": dict(scene_state),
                "synthetic": synthetic,
                "created_at": now,
                "extracted_at": now,
            }
        )

        capture_by_scene = {
            e["provenance"]["scene_id"]: e["capture_time"] for e in entry["epochs"]
        }
        for art, acq in zip(entry["artifacts"], entry["acquisitions"]):
            observations.append(
                {
                    # Scene identity is part of the id: two scenes can share pixel
                    # content (one artifact id) yet be distinct catalog observations.
                    "observation_id": _fid(
                        "obs",
                        "site_imagery_scene",
                        producer_ent,
                        art["scene_id"],
                        art["artifact_id"],
                    ),
                    "source_id": sid,
                    "entity_id": ent_id,
                    "observation_type": "satellite_scene",
                    "observed_at": capture_by_scene[art["scene_id"]],
                    "location": location,
                    "attributes": {
                        **common,
                        "scene_id": art["scene_id"],
                        "provider": art["provider"],
                        "collection": art["collection"],
                        "platform": art["platform"],
                        "instrument": art["instrument"],
                        "artifact_id": art["artifact_id"],
                        "content_sha256": art["content_sha256"],
                        "cloud_cover_pct": art["cloud_cover_pct"],
                        "resolution_m": art["resolution_m"],
                        "geometric_confidence": art["geometric_confidence"],
                        "acquisition_receipt_id": acq["receipt_id"],
                    },
                    "confidence": min(art["geometric_confidence"], cap),
                    "lineage": _site_imagery_lineage(
                        "SITE_IMAGERY_SCENE", doc_sha, document
                    ),
                    "evidence_state": dict(scene_state),
                    "synthetic": synthetic,
                    "created_at": now,
                    "extracted_at": now,
                }
            )

        for cmp in entry["comparisons"]:
            # Unknown and same-epoch pairs make no claim, so they are not exported.
            if cmp["disposition"] != "SCORED":
                continue
            signal = cmp["signal"]
            result = signal["result"]
            score = result["score"]
            observations.append(
                {
                    "observation_id": _fid(
                        "obs", "site_imagery_change", cmp["comparison_id"]
                    ),
                    "source_id": sid,
                    "entity_id": ent_id,
                    "observation_type": "satellite_visible_change",
                    "observed_at": capture_by_scene[result["after"]["scene_id"]],
                    "location": location,
                    "attributes": {
                        **common,
                        "comparison_id": cmp["comparison_id"],
                        "pair_kind": cmp["pair_kind"],
                        "epoch_class": cmp["epoch_class"],
                        "classification": score["classification"],
                        "change_types": score["change_types"],
                        "adjusted_change_score": score["adjusted_change_score"],
                        "review_required": result["review_required"],
                        "review_reasons": result["review_reasons"],
                        "review_status": signal["review_status"],
                        "signal_id": signal["signal_id"],
                        "method": signal["method"],
                        "method_version": signal["method_version"],
                        "before_scene_id": result["before"]["scene_id"],
                        "after_scene_id": result["after"]["scene_id"],
                        "before_artifact_id": result["before"]["artifact_id"],
                        "after_artifact_id": result["after"]["artifact_id"],
                        "guardrail": "VISIBLE_EPOCH_CHANGE_ONLY",
                    },
                    "confidence": signal["confidence"],
                    "lineage": _site_imagery_lineage(
                        "SITE_IMAGERY_CHANGE", doc_sha, document
                    ),
                    "evidence_state": dict(change_state),
                    "synthetic": synthetic,
                    "created_at": now,
                    "extracted_at": now,
                }
            )
    return {"sources": [source], "entities": entities, "observations": observations}


def merge_site_imagery(
    streams: dict[str, list[dict]], lane: dict[str, list[dict]]
) -> None:
    """Fold the site imagery lane into the canonical streams, in place (idempotent)."""
    for stream, id_field in (("sources", "source_id"), ("entities", "entity_id"),
                             ("observations", "observation_id")):
        known = {row[id_field] for row in streams.setdefault(stream, [])}
        for row in lane[stream]:
            if row[id_field] not in known:
                streams[stream].append(row)
                known.add(row[id_field])


# --------------------------------------------------------------------------
# source_monitors stream (thehub-pr ADR 0013). One row per source that this
# repo's two source registries say it monitors. A missing-persons entry marked
# `federation_eligible: false` (raw PII, ToS-restricted, tip-stream stratum C)
# is never emitted, not even as a monitor row.
#
# Name, family, tier, cadence, window and declared status reproduce thehub-pr's
# registry reader (src/hub/source_monitor.py: _parse_spiderweb_hydrography,
# _parse_spiderweb_missing_persons, normalize_cadence, normalize_status,
# normalize_tier, cadence_from_seconds, _window), so nothing the Hub shows
# changes when it starts reading this producer from the stream. They say what
# the registry declares; they are not a health check.
#
# When a source last succeeded comes only from a run receipt in
# data/source_run_state.json (prii_export_utils.record_run; RUN_RECEIPT). No
# fetcher writes one yet, and no committed output carries a per-source retrieval
# time (hydrography snapshots and harvester outputs stay out of git), so every
# source is NOT_RECORDED with a null time. Nothing here reads file or git dates.
# --------------------------------------------------------------------------
SOURCE_MONITOR_REGISTRIES = {
    "hydrography": "manifests/pr_hydrography/source_registry.csv",
    "missing_persons": "configs/missing_persons_sources.yaml",
}
SOURCE_RUN_STATE = "data/source_run_state.json"
_HYDROGRAPHY_COLUMNS = (
    "source_id", "authority", "universe", "refresh_policy", "evidence_tier",
)
# Nominal window per named cadence (hub CADENCE_WINDOW_SECONDS); event, static,
# manual and unknown have none.
_MONITOR_WINDOWS = {
    "realtime": 3600, "hourly": 3600, "daily": 86400, "weekly": 7 * 86400,
    "monthly": 31 * 86400, "quarterly": 92 * 86400, "yearly": 366 * 86400,
}
# The hub's _NAMED_CADENCE / _NAMED_STATUS entries for this repo's vocabularies.
# tests/test_federation_source_monitors.py fails on a committed registry value
# that is not mapped here.
_REFRESH_POLICY_CADENCE = {
    "pin_by_vintage": "static",
    "probe_service_then_snapshot_if_changed": "event",
    "probe_sciencebase_item_then_snapshot_if_changed": "event",
}
_MISSING_PERSONS_STATUS = {
    "harvester_landed": "active",
    "harvester_planned": "not_active",
    "manual_pull": "manual",
    "aggregate_only": "partial",
    "cannot_reach": "inactive",
}
_MONITOR_TIERS = ("T1", "T2", "T3", "T4")


def _monitor_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _named(raw: Any, vocabulary: dict[str, str]) -> str:
    if raw is None:
        return "unknown"
    return vocabulary.get(str(raw).strip().lower(), "unknown")


def _monitor_tier(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().upper()
    return value if value in _MONITOR_TIERS else None


def _cadence_from_seconds(seconds: Any) -> str:
    """Largest-first buckets with the hub's 25% tolerance (90 days is quarterly)."""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 0:
        return "unknown"
    for name in ("yearly", "quarterly", "monthly", "weekly", "daily", "hourly"):
        if value * 1.25 >= _MONITOR_WINDOWS[name]:
            return name
    return "realtime"


def _monitor_window(cadence: str, declared_seconds: Any = None) -> int | None:
    """A declared window in seconds wins; otherwise the cadence's nominal one."""
    try:
        declared = float(declared_seconds) if declared_seconds is not None else 0.0
    except (TypeError, ValueError):
        declared = 0.0
    if declared > 0:
        return int(declared)
    return _MONITOR_WINDOWS.get(cadence)


def _hydrography_monitors(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        missing = [c for c in _HYDROGRAPHY_COLUMNS if c not in fields]
        if missing:
            raise ValueError(f"{path}: missing column(s): {', '.join(missing)}")
        rows = list(reader)
    out = []
    for r in rows:
        cadence = _named(r["refresh_policy"], _REFRESH_POLICY_CADENCE)
        out.append({
            "source_ref": r["source_id"],
            "name": _monitor_text(f"{r['authority']}: {r['universe']}"),
            "producer_family": _monitor_text(r["universe"]),
            "evidence_tier": _monitor_tier(r["evidence_tier"]),
            "cadence": cadence,
            "cadence_window_seconds": _monitor_window(cadence),
            "declared_status": "unknown",
            "source_url": _monitor_text(r.get("endpoint")),
        })
    return out


def _missing_persons_monitors(path: Path) -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:  # not a base dependency; the airspace extra has it
        raise RuntimeError(f"reading {path} needs PyYAML") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, dict):
        raise ValueError(f"{path}: expected a top-level 'sources' mapping")
    out = []
    for sid, s in sources.items():
        if not isinstance(s, dict):
            raise ValueError(f"{path}: source {sid!r} is not a mapping")
        # Only the three options the registry documents (true, false,
        # aggregate_only); anything else fails rather than guess at eligibility.
        eligible = s.get("federation_eligible")
        if not (eligible is True or eligible is False or eligible == "aggregate_only"):
            raise ValueError(f"{path}: {sid!r} federation_eligible={eligible!r}")
        if eligible is False:
            continue
        days = s.get("refresh_cadence_days")
        positive = isinstance(days, (int, float)) and days > 0
        seconds = float(days) * 86400 if positive else None
        # 0 days marks a one-off dataset or a per-event backfill: nothing recurs.
        cadence = "static" if days == 0 else _cadence_from_seconds(seconds)
        out.append({
            "source_ref": sid,
            "name": _monitor_text(s.get("operator")) or _monitor_text(sid),
            "producer_family": "missing_persons",
            "evidence_tier": None,
            "cadence": cadence,
            "cadence_window_seconds": _monitor_window(cadence, seconds),
            "declared_status": _named(s.get("status"), _MISSING_PERSONS_STATUS),
            "source_url": _monitor_text(s.get("url")),
        })
    return out


_MONITOR_READERS = {
    "hydrography": _hydrography_monitors,
    "missing_persons": _missing_persons_monitors,
}


def build_source_monitors(
    now: str,
    *,
    repo_root: Path = REPO_ROOT,
    run_state_path: Path | None = None,
) -> list[dict[str, Any]]:
    """The ``source_monitors`` stream: one row per registered source, by source id."""
    state_path = run_state_path or repo_root / SOURCE_RUN_STATE
    state = SourceRunState.load(state_path)
    inputs = [*SOURCE_MONITOR_REGISTRIES.values(), SOURCE_RUN_STATE]
    rows: dict[str, dict[str, Any]] = {}
    for key, rel in SOURCE_MONITOR_REGISTRIES.items():
        for entry in _MONITOR_READERS[key](repo_root / rel):
            ref = _monitor_text(entry.pop("source_ref"))
            if not ref:
                raise ValueError(f"{rel}: source without an id")
            if ref in rows:
                raise ValueError(f"duplicate source id {ref!r} across registries")
            receipt = state.get(ref) or {}
            at, basis = resolve_last_success(receipt, None)
            rows[ref] = source_monitor_row(
                producer=PRODUCER, source_ref=ref, registry_path=rel,
                lineage=_lineage("SOURCE_MONITOR", inputs, "registry_projection"),
                created_at=now, extracted_at=now,
                last_success_at=at, last_success_basis=basis,
                last_attempt_at=receipt.get("last_attempt_at"),
                last_attempt_status=receipt.get("last_attempt_status"),
                **entry,
            )
    return [rows[k] for k in sorted(rows)]


def _rel(src_ent, rtype, tgt_ent, sid, score, synthetic, created, now):
    rid = _fid("rel", src_ent, rtype, tgt_ent)
    return {rid: {
        "relationship_id": rid, "source_id": sid, "source_entity_id": src_ent,
        "target_entity_id": tgt_ent, "relationship_type": rtype, "evidence_source_id": sid,
        "confidence": score, "lineage": _lineage("RELATIONSHIP"),
        "synthetic": synthetic, "created_at": created, "extracted_at": now,
        # reported_by is documented by the record itself; "observed" links a
        # record to a callsign-keyed aircraft and is not given a class.
        "evidence_state": _evidence_state(epistemic_class="CURATED" if rtype == "reported_by" else None),
    }}


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
                    help="explicit verified moneysweep-pr canonical export package for PPP geometry")
    ap.add_argument("--no-ppp-geometry", action="store_true",
                    help="Skip the PPP geometry lane even if a producer package is supplied.")
    ap.add_argument("--site-imagery-timeline", default=None,
                    help="site imagery timeline document (JSON) to export as a "
                         "provisional lane; an invalid document fails the export")
    args = ap.parse_args()

    pkg = Path(args.package)
    sources_in = _read_stream(pkg, "sources")
    records = {name: _read_stream(pkg, name) for name in RECORD_STREAMS}
    if not sources_in and not any(records.values()) and not args.site_imagery_timeline:
        print(f"no envelope streams found in {pkg} — nothing to export")
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    streams = build_streams(sources_in, records, now)
    streams["source_monitors"] = build_source_monitors(now)

    if not args.no_ppp_geometry:
        try:
            from readiness.ppp_geometry import resolve_projects

            resolution = resolve_projects(args.moneysweep_package)
        except Exception as exc:  # noqa: BLE001 - optional lane is fail-closed and isolated
            print(f"PPP geometry lane skipped: {exc}", file=sys.stderr)
        else:
            merge_ppp_geometry(streams, build_ppp_geometry_streams(resolution, now))
            if resolution["unresolved_count"]:
                print(
                    f"PPP geometry: {resolution['resolved_count']} resolved, "
                    f"{resolution['unresolved_count']} left in the geocode queue",
                    file=sys.stderr,
                )

    if args.site_imagery_timeline:
        try:
            document = json.loads(Path(args.site_imagery_timeline).read_text())
            from spiderweb.site_timeline.timeline import validate_document

            problems = validate_document(document)
        except (OSError, ValueError) as exc:
            print(f"FAIL — site imagery timeline unreadable: {exc}", file=sys.stderr)
            return 2
        if problems:
            print(
                f"FAIL — site imagery timeline invalid ({len(problems)} problems):",
                file=sys.stderr,
            )
            for problem in problems[:20]:
                print(f"  - {problem}", file=sys.stderr)
            return 2
        merge_site_imagery(streams, build_site_imagery_streams(document, now))

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
