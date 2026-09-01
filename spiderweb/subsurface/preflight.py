"""ArcGIS source preflight: schema, OID, limits, and immutable metadata receipts."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from .sources import SourceKind, SourceSpec

@dataclass(frozen=True)
class ArcGISLayerManifest:
    source_id: str
    metadata_url: str
    retrieved_utc: str
    byte_sha256: str
    logical_sha256: str
    layer_name: str
    geometry_type: str | None
    object_id_field: str
    max_record_count: int
    has_z: bool
    has_m: bool
    spatial_reference: dict
    fields: tuple[dict, ...]
    supported_query_formats: str


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def freeze_arcgis_layer_manifest(
    spec: SourceSpec, *, fetch, snapshot_dir: str | Path | None = None
) -> ArcGISLayerManifest:
    if spec.kind != SourceKind.ARCGIS_LAYER:
        raise ValueError("ArcGIS preflight requires ARCGIS_LAYER")
    url = f"{spec.endpoint.rstrip('/')}/{spec.layer_id}?{urlencode({'f': 'json'})}"
    raw = fetch(url)
    obj = json.loads(raw)
    if "error" in obj:
        raise RuntimeError(f"ArcGIS metadata query failed for {spec.source_id}: {obj['error']}")
    oid = obj.get("objectIdField") or obj.get("objectIdFieldName")
    if not oid:
        fields = obj.get("fields", [])
        oid = next((f.get("name") for f in fields if f.get("type") == "esriFieldTypeOID"), None)
    if not oid:
        raise RuntimeError(f"ArcGIS layer {spec.source_id} exposes no OID field")
    fields = tuple(dict(field) for field in obj.get("fields", []))
    manifest = ArcGISLayerManifest(
        source_id=spec.source_id,
        metadata_url=url,
        retrieved_utc=datetime.now(timezone.utc).isoformat(),
        byte_sha256=_sha(raw),
        logical_sha256=_sha(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()),
        layer_name=str(obj.get("name", "")),
        geometry_type=obj.get("geometryType"),
        object_id_field=str(oid),
        max_record_count=int(obj.get("maxRecordCount") or 0),
        has_z=bool(obj.get("hasZ", False)),
        has_m=bool(obj.get("hasM", False)),
        spatial_reference=dict((obj.get("extent") or {}).get("spatialReference") or {}),
        fields=fields,
        supported_query_formats=str(obj.get("supportedQueryFormats", "")),
    )
    if snapshot_dir is not None:
        target = Path(snapshot_dir) / spec.source_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "layer_metadata.raw.json").write_bytes(raw)
        (target / "layer_manifest.json").write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True), encoding="utf-8"
        )
        query_contract = {
            "where": "1=1",
            "geometry": "AOI_BBOX",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outSR": 4326,
            "orderByFields": f"{manifest.object_id_field} ASC",
            "paging": "resultOffset/resultRecordCount",
            "count_preflight": True,
        }
        (target / "query_contract.json").write_text(
            json.dumps(query_contract, indent=2, sort_keys=True), encoding="utf-8"
        )
    return manifest
