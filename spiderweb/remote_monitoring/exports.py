"""Emit the ``rm_*`` output layers as GeoJSON with provenance.

The backbone writes compact GeoJSON FeatureCollections (not GPKG) so the core
stays geopandas-free and the emitted layers are diff-friendly and testable. Each
Feature carries the standard ``properties._meta`` block
(``provenance_utils.geojson_feature_meta``) and each export writes an
``rm_manifest.json`` stamped with the canonical reproducibility record
(``provenance_utils.attach_to_manifest``). A GPKG sink into ``PRI.gpkg`` is a
later phase; these same layer names (``rm_monitoring_aois``, ``rm_observations``,
``rm_change_candidates``, ``rm_adjudications``, ``rm_contract_crosswalk``) carry
over to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import schemas

PRODUCER_MODULE = "spiderweb.remote_monitoring.exports"

# Layer id -> output filename.
LAYER_FILES = {
    "rm_monitoring_aois": "rm_monitoring_aois.geojson",
    "rm_observations": "rm_observations.geojson",
    "rm_change_candidates": "rm_change_candidates.geojson",
    "rm_adjudications": "rm_adjudications.geojson",
    "rm_contract_crosswalk": "rm_contract_crosswalk.geojson",
}


def _meta_block(source_artifact: str) -> Dict[str, str]:
    from provenance_utils import geojson_feature_meta

    return geojson_feature_meta(
        producer_module=PRODUCER_MODULE, source_artifact=source_artifact
    )


def _feature(
    geometry: Dict[str, Any], properties: Dict[str, Any], source: str
) -> Dict[str, Any]:
    props = dict(properties)
    props["_meta"] = _meta_block(source)
    return {"type": "Feature", "geometry": geometry, "properties": props}


def _point_from_centroid(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a polygon AOI/observation to a representative point for non-geo layers."""
    try:
        ring = geometry["coordinates"][0]
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        return {
            "type": "Point",
            "coordinates": [
                round(sum(lons) / len(lons), 6),
                round(sum(lats) / len(lats), 6),
            ],
        }
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return geometry


def aoi_features(aois: Iterable[Any]) -> List[Dict[str, Any]]:
    feats = []
    for aoi in aois:
        props = {
            "aoi_uid": aoi.aoi_uid,
            "name": aoi.name,
            "aoi_class": aoi.aoi_class,
            "monitoring_objective": aoi.monitoring_objective,
            "municipio": aoi.municipio,
            "priority": aoi.priority,
            "active": aoi.active,
            "layer_id": schemas.LAYER_ID,
            "node_type": schemas.AOI_NODE_TYPE,
        }
        feats.append(_feature(aoi.geometry, props, "rm_monitoring_aois"))
    return feats


def observation_features(observations: Iterable[Any]) -> List[Dict[str, Any]]:
    feats = []
    for obs in observations:
        rec = obs.to_record() if hasattr(obs, "to_record") else dict(obs)
        geom = rec.get("geometry") or {}
        props = {k: v for k, v in rec.items() if k != "geometry"}
        props["layer_id"] = schemas.LAYER_ID
        props["node_type"] = schemas.OBSERVATION_NODE_TYPE
        feats.append(_feature(_point_from_centroid(geom), props, "rm_observations"))
    return feats


def _record_features(records: Iterable[Any], source: str) -> List[Dict[str, Any]]:
    """Non-geometric records (adjudications, crosswalks) as null-geometry features."""
    feats = []
    for rec in records:
        data = rec.to_record() if hasattr(rec, "to_record") else dict(rec)
        feats.append(
            {
                "type": "Feature",
                "geometry": None,
                "properties": {**data, "_meta": _meta_block(source)},
            }
        )
    return feats


def _write_collection(path: Path, name: str, features: List[Dict[str, Any]]) -> None:
    from provenance_utils import feature_collection_summary

    fc = {
        "type": "FeatureCollection",
        "name": name,
        "metadata": {
            "layer_id": schemas.LAYER_ID,
            "subsystem": schemas.SUBSYSTEM,
            "summary": feature_collection_summary(
                [f for f in features if f.get("geometry")]
            ),
        },
        "features": features,
    }
    path.write_text(json.dumps(fc, indent=2), encoding="utf-8")


def export_layers(
    output_dir: str,
    *,
    aois: Optional[Iterable[Any]] = None,
    observations: Optional[Iterable[Any]] = None,
    change_candidates: Optional[Iterable[Any]] = None,
    adjudications: Optional[Iterable[Any]] = None,
    crosswalks: Optional[Iterable[Any]] = None,
    command: Optional[str] = None,
) -> Dict[str, Any]:
    """Write the requested ``rm_*`` layers + ``rm_manifest.json`` to ``output_dir``.

    Returns a summary dict with the written paths and per-layer feature counts,
    including the reproducibility block from ``provenance_utils``.
    """
    from provenance_utils import attach_to_manifest

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: Dict[str, str] = {}
    counts: Dict[str, int] = {}

    layer_features = {
        "rm_monitoring_aois": aoi_features(aois) if aois is not None else None,
        "rm_observations": (
            observation_features(observations) if observations is not None else None
        ),
        "rm_change_candidates": (
            observation_features(change_candidates)
            if change_candidates is not None
            else None
        ),
        "rm_adjudications": (
            _record_features(adjudications, "rm_adjudications")
            if adjudications is not None
            else None
        ),
        "rm_contract_crosswalk": (
            _record_features(crosswalks, "rm_contract_crosswalk")
            if crosswalks is not None
            else None
        ),
    }

    for layer_id, feats in layer_features.items():
        if feats is None:
            continue
        path = out / LAYER_FILES[layer_id]
        _write_collection(path, layer_id, feats)
        written[layer_id] = str(path)
        counts[layer_id] = len(feats)

    manifest: Dict[str, Any] = {
        "subsystem": schemas.SUBSYSTEM,
        "layer_id": schemas.LAYER_ID,
        "layers_written": written,
        "feature_counts": counts,
    }
    attach_to_manifest(
        manifest, command=command or "spiderweb.remote_monitoring.export_layers"
    )
    manifest_path = out / "rm_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
