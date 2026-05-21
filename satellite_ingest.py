"""
SATELLITE INGEST  —  PRII Stage 3 runtime ingestion

Turns a catalog of satellite/remote-sensing scenes into validated
`satellite_source_manifest` documents (see
docs/contracts/SATELLITE_SOURCE_MANIFEST.md). Every manifest is checked
against schemas/satellite_source_manifest.schema.json before it is written —
the contract is fail-closed, so envelope violations, fixture-mode violations
and missing fields are routed to a rejected/ directory instead of the
manifests/ output.

Two catalog sources are supported:

  synthetic   A local JSON catalog ({"scenes": [...]}). Fully offline; this
              is the default and what CI exercises.
  stac        A STAC ItemCollection — either a local JSON file or an HTTP(S)
              STAC API URL. STAC items are mapped to scenes with documented
              default enrichment. A bearer token may be supplied via the
              SAT_STAC_TOKEN environment variable.

This module performs no raster download or image processing — it produces and
validates source metadata only.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from schema_validation import SchemaValidator

SCHEMA_NAME = "satellite_source_manifest"
SCHEMA_VERSION = "1.0"
PIPELINE_VERSION = "1.0.0"
DEFAULT_PRODUCER = "spiderweb-sat-ingest"

# Puerto Rico operating envelope — mirrors the schema's prCoordinate bounds.
PR_ENVELOPE = {"lon_min": -68.2, "lon_max": -65.1, "lat_min": 17.8, "lat_max": 18.7}

# Scene blocks copied verbatim into the manifest.
_SCENE_BLOCKS = ("source", "acquisition", "asset", "geometry", "puerto_rico", "quality")


class SatelliteIngestError(Exception):
    """Raised for catalog-loading problems (bad path, malformed JSON, etc.)."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(value: str) -> str:
    keep = [c if (c.isalnum() or c in "-_.") else "_" for c in (value or "scene")]
    return "".join(keep) or "scene"


# ── Catalog loaders ───────────────────────────────────────────────────────────

def load_synthetic_catalog(path: str) -> List[dict]:
    """Load a synthetic catalog: {"scenes": [...]} (or a bare list of scenes)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SatelliteIngestError(f"catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SatelliteIngestError(f"catalog is not valid JSON: {path}") from exc

    scenes = doc.get("scenes", doc) if isinstance(doc, dict) else doc
    if not isinstance(scenes, list):
        raise SatelliteIngestError("synthetic catalog must contain a 'scenes' list")
    return scenes


def load_stac_catalog(source: str) -> List[dict]:
    """Load a STAC ItemCollection from an HTTP(S) URL or a local JSON file."""
    if source.startswith(("http://", "https://")):
        import requests

        headers = {}
        token = os.environ.get("SAT_STAC_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(source, headers=headers, timeout=30)
        resp.raise_for_status()
        doc = resp.json()
    else:
        try:
            doc = json.loads(Path(source).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SatelliteIngestError(f"STAC catalog not found: {source}") from exc
        except json.JSONDecodeError as exc:
            raise SatelliteIngestError(f"STAC catalog is not valid JSON: {source}") from exc

    items = doc.get("features") or doc.get("items") or []
    return [_stac_item_to_scene(item) for item in items]


def _stac_item_to_scene(item: dict) -> dict:
    """Map a STAC Item to a scene dict, enriching with documented defaults.

    STAC items do not carry Puerto Rico region or reliability metadata, so
    those fields fall back to conservative defaults (`full_island`,
    `unverified`). An item without a 64-hex sha256 checksum will be rejected
    by schema validation — that is the intended fail-closed behaviour.
    """
    props = item.get("properties", {}) or {}
    assets = item.get("assets", {}) or {}
    asset = (
        assets.get("data")
        or assets.get("visual")
        or next(iter(assets.values()), {})
    )
    instruments = props.get("instruments") or [props.get("instrument", "unknown")]
    return {
        "scene_id": item.get("id", ""),
        "synthetic": False,
        "source": {
            "provider": props.get("provider") or props.get("constellation") or "unknown",
            "collection": item.get("collection") or props.get("collection") or "unknown",
            "platform": props.get("platform") or "unknown",
            "instrument": instruments[0] if instruments else "unknown",
        },
        "acquisition": {
            "acquired_at": props.get("datetime") or props.get("start_datetime") or "",
            "processed_at": props.get("updated") or props.get("created")
            or props.get("datetime") or "",
            "license": props.get("license") or "unspecified",
        },
        "asset": {
            "source_uri": asset.get("href", ""),
            "checksum_sha256": asset.get("file:checksum_sha256")
            or props.get("file:checksum_sha256") or "",
            "media_type": asset.get("type") or "image/tiff",
        },
        "geometry": {
            "crs": "EPSG:4326",
            "footprint": item.get("geometry") or {},
            "bbox": item.get("bbox") or [],
        },
        "puerto_rico": {"region": props.get("pr:region") or "full_island"},
        "quality": {
            "cloud_cover_pct": float(props.get("eo:cloud_cover") or 0.0),
            "geometric_confidence": float(props.get("geometric_confidence") or 0.8),
            "source_reliability": props.get("source_reliability") or "unverified",
        },
    }


# ── Ingestor ──────────────────────────────────────────────────────────────────

class SatelliteIngestor:
    """Builds, validates, and writes satellite_source_manifest documents."""

    def __init__(self, output_dir: str, producer: str = DEFAULT_PRODUCER):
        self.output_dir = Path(output_dir)
        self.producer = producer
        self._validator = SchemaValidator()

    def build_manifest(self, scene: dict) -> dict:
        """Wrap a scene in the manifest envelope (ids, timestamps, lineage)."""
        scene_id = scene.get("scene_id") or scene.get("manifest_id") or ""
        manifest: Dict[str, Any] = {
            "manifest_id": scene_id,
            "schema_version": SCHEMA_VERSION,
            "producer": self.producer,
            "created_at": _utc_now(),
            "synthetic": bool(scene.get("synthetic", True)),
        }
        if scene.get("notes") is not None:
            manifest["notes"] = scene["notes"]
        for block in _SCENE_BLOCKS:
            if block in scene:
                manifest[block] = scene[block]
        manifest["lineage"] = scene.get("lineage") or {
            "processing_pipeline": self.producer,
            "pipeline_version": PIPELINE_VERSION,
            "derived_from": [],
        }
        return manifest

    def ingest(self, scenes: List[dict]) -> dict:
        """Validate every scene's manifest; write passes and rejects; summarise."""
        manifests_dir = self.output_dir / "manifests"
        rejected_dir = self.output_dir / "rejected"
        manifests_dir.mkdir(parents=True, exist_ok=True)

        validated: List[str] = []
        rejected: List[dict] = []

        for index, scene in enumerate(scenes):
            manifest = self.build_manifest(scene)
            result = self._validator.validate(manifest, SCHEMA_NAME)
            scene_id = scene.get("scene_id") or manifest["manifest_id"] or f"scene_{index}"

            if result["valid"]:
                (manifests_dir / f"{_safe_name(manifest['manifest_id'])}.json").write_text(
                    json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
                )
                validated.append(manifest["manifest_id"])
            else:
                rejected_dir.mkdir(parents=True, exist_ok=True)
                record = {
                    "scene_id": scene_id,
                    "errors": result["errors"],
                    "manifest": manifest,
                }
                (rejected_dir / f"{_safe_name(scene_id)}.json").write_text(
                    json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
                )
                rejected.append({"scene_id": scene_id, "errors": result["errors"]})

        summary = {
            "generated_at": _utc_now(),
            "producer": self.producer,
            "schema": SCHEMA_NAME,
            "pr_envelope": PR_ENVELOPE,
            "catalogued": len(scenes),
            "validated": len(validated),
            "rejected": len(rejected),
            "manifests": sorted(validated),
            "rejected_scenes": rejected,
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "ingest_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        return summary


def ingest_satellite(output_dir: str, catalog: str, source: str = "synthetic",
                     producer: str = DEFAULT_PRODUCER) -> dict:
    """Load a catalog, run ingestion, and return the summary dict."""
    if source == "stac":
        scenes = load_stac_catalog(catalog)
    else:
        scenes = load_synthetic_catalog(catalog)
    return SatelliteIngestor(output_dir, producer=producer).ingest(scenes)


def main() -> None:
    parser = argparse.ArgumentParser(description="PRII Stage 3 satellite source ingestion")
    parser.add_argument("output_dir", help="Directory for manifests/ + ingest_summary.json")
    parser.add_argument("--catalog", required=True,
                        help="Catalog path (synthetic JSON, or STAC file/URL)")
    parser.add_argument("--source", choices=["synthetic", "stac"], default="synthetic",
                        help="Catalog source type (default: synthetic)")
    parser.add_argument("--producer", default=DEFAULT_PRODUCER,
                        help=f"Producer name written to manifests (default: {DEFAULT_PRODUCER})")
    args = parser.parse_args()

    try:
        summary = ingest_satellite(args.output_dir, args.catalog, args.source, args.producer)
    except SatelliteIngestError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  catalogued: {summary['catalogued']}")
    print(f"  validated:  {summary['validated']}")
    print(f"  rejected:   {summary['rejected']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
