"""Fail-closed CRIM parcel lookup adapter for Spiderweb-PR.

The adapter treats the Puerto Rico CRIM/SIGE ArcGIS parcel layer as an
authoritative *source manifestation* for parcel identifiers and geometry. It
never infers ownership, title, valuation, or tax status from this layer.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping

LAYER_URL = "https://sigejp.pr.gov/server/rest/services/crim/crim_parcelas/MapServer/0"
QUERY_URL = f"{LAYER_URL}/query"
ADAPTER_VERSION = "0.1.0"
REQUIRED_FIELDS = {"OBJECTID", "GLOBALID", "NUM_CATASTRO", "OLDPID", "TIPO", "CATEGORIA"}
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class LookupMode(str, Enum):
    NUM_CATASTRO = "NUM_CATASTRO"
    OLDPID = "OLDPID"
    GLOBALID = "GLOBALID"
    OBJECTID = "OBJECTID"
    POINT = "POINT"
    BBOX = "BBOX"


class LookupState(str, Enum):
    MATCH = "MATCH"
    VALID_ZERO_RESULT = "VALID_ZERO_RESULT"
    MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
    INVALID_INPUT = "INVALID_INPUT"
    SOURCE_ERROR = "SOURCE_ERROR"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    TRUNCATED = "TRUNCATED"
    UNRESOLVED = "UNRESOLVED"


class IdentityState(str, Enum):
    CERTIFIED = "CERTIFIED"
    PROVISIONAL = "PROVISIONAL"
    CANDIDATE_NOT_IDENTITY = "CANDIDATE_NOT_IDENTITY"
    UNRESOLVED = "UNRESOLVED"


class CrimError(RuntimeError):
    """Base CRIM adapter error."""


class SourceTransportError(CrimError):
    pass


class SourceResponseError(CrimError):
    pass


class SchemaDriftError(CrimError):
    pass


class PaginationError(CrimError):
    pass


class InvalidInputError(CrimError):
    pass


@dataclass(frozen=True)
class HttpResult:
    status: int
    content_type: str
    body: bytes
    url: str
    attempts: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Provenance:
    endpoint: str
    retrieval_utc: str
    http_status: int
    content_type: str
    response_size: int
    response_sha256: str
    request_sha256: str
    adapter_version: str = ADAPTER_VERSION


@dataclass
class LookupResult:
    state: LookupState
    mode: LookupMode
    match_count: int
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)
    identity_state: IdentityState = IdentityState.UNRESOLVED


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def normalize_identifier(value: Any) -> str:
    if value is None:
        raise InvalidInputError("identifier is required")
    text = str(value).strip()
    if not text:
        raise InvalidInputError("identifier must not be empty")
    if len(text) > 256:
        raise InvalidInputError("identifier is unreasonably long")
    return text


def validate_lon_lat(lon: float, lat: float) -> tuple[float, float, list[str]]:
    try:
        lon_f, lat_f = float(lon), float(lat)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("longitude and latitude must be numeric") from exc
    if not -180 <= lon_f <= 180 or not -90 <= lat_f <= 90:
        raise InvalidInputError("coordinates outside WGS84 range")
    warnings: list[str] = []
    if not (-68.1 <= lon_f <= -65.0 and 17.5 <= lat_f <= 18.8):
        if 17.5 <= lon_f <= 18.8 and -68.1 <= lat_f <= -65.0:
            warnings.append("coordinates appear to be latitude/longitude swapped")
        else:
            warnings.append("coordinates are outside the Puerto Rico sanity window")
    return lon_f, lat_f, warnings


def validate_layer_metadata(metadata: Mapping[str, Any]) -> None:
    if metadata.get("id") != 0:
        raise SchemaDriftError(f"unexpected CRIM layer id: {metadata.get('id')!r}")
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise SchemaDriftError(f"unexpected geometry type: {metadata.get('geometryType')!r}")
    field_names = {f.get("name") for f in metadata.get("fields", []) if isinstance(f, Mapping)}
    missing = sorted(REQUIRED_FIELDS - field_names)
    if missing:
        raise SchemaDriftError(f"required fields missing: {', '.join(missing)}")
    sr = metadata.get("sourceSpatialReference") or metadata.get("extent", {}).get("spatialReference", {})
    if sr.get("wkid") != 32161 and sr.get("latestWkid") != 32161:
        raise SchemaDriftError(f"unexpected native CRS: {sr!r}")


Transport = Callable[[str, Mapping[str, Any]], HttpResult]


class CrimClient:
    def __init__(self, transport: Transport | None = None, *, timeout: float = 30.0, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.transport = transport or self._http_get

    def _http_get(self, url: str, params: Mapping[str, Any]) -> HttpResult:
        encoded = urllib.parse.urlencode([(k, str(v)) for k, v in params.items() if v is not None])
        full_url = f"{url}?{encoded}"
        attempts: list[dict[str, Any]] = []
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                req = urllib.request.Request(full_url, headers={"User-Agent": "Spiderweb-PR CRIM Lookup/0.1"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    status = int(getattr(resp, "status", 200))
                    content_type = resp.headers.get("Content-Type", "")
                    attempts.append({"attempt": attempt + 1, "status": status, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)})
                    return HttpResult(status, content_type, body, full_url, tuple(attempts))
            except urllib.error.HTTPError as exc:
                attempts.append({"attempt": attempt + 1, "status": exc.code, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)})
                if exc.code not in RETRYABLE_HTTP or attempt >= self.retries:
                    raise SourceTransportError(f"CRIM HTTP {exc.code} after {attempt + 1} attempt(s)") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                attempts.append({"attempt": attempt + 1, "error": type(exc).__name__, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)})
                if attempt >= self.retries:
                    raise SourceTransportError(f"CRIM transport failure after {attempt + 1} attempt(s): {exc}") from exc
            time.sleep(min(0.25 * (2**attempt), 2.0))
        raise AssertionError("unreachable")

    def _decode(self, result: HttpResult, params: Mapping[str, Any]) -> tuple[dict[str, Any], Provenance]:
        request_identity = canonical_json({"endpoint": result.url.split("?", 1)[0], "params": dict(params)})
        prov = Provenance(
            endpoint=result.url.split("?", 1)[0],
            retrieval_utc=utc_now(),
            http_status=result.status,
            content_type=result.content_type,
            response_size=len(result.body),
            response_sha256=sha256_bytes(result.body),
            request_sha256=sha256_bytes(request_identity),
        )
        if result.status != 200:
            raise SourceResponseError(f"unexpected CRIM HTTP status {result.status}")
        try:
            payload = json.loads(result.body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceResponseError("CRIM response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SourceResponseError("CRIM response must be a JSON object")
        if "error" in payload:
            raise SourceResponseError(f"ArcGIS service error: {payload['error']!r}")
        return payload, prov

    def metadata(self) -> tuple[dict[str, Any], Provenance]:
        params = {"f": "pjson"}
        payload, prov = self._decode(self.transport(LAYER_URL, params), params)
        validate_layer_metadata(payload)
        return payload, prov

    def query(self, params: Mapping[str, Any]) -> tuple[dict[str, Any], Provenance]:
        full = {"f": "json", **dict(params)}
        return self._decode(self.transport(QUERY_URL, full), full)

    def count(self, where: str = "1=1") -> tuple[int, Provenance]:
        payload, prov = self.query({"where": where, "returnCountOnly": "true"})
        count = payload.get("count")
        if not isinstance(count, int) or count < 0:
            raise SourceResponseError("count query returned invalid count")
        return count, prov

    def object_ids(self, where: str = "1=1") -> tuple[list[int], Provenance]:
        payload, prov = self.query({"where": where, "returnIdsOnly": "true"})
        ids = payload.get("objectIds")
        if ids is None:
            ids = []
        if not isinstance(ids, list) or any(not isinstance(x, int) for x in ids):
            raise SourceResponseError("object id query returned invalid objectIds")
        if len(ids) != len(set(ids)):
            raise PaginationError("duplicate OBJECTID values in returnIdsOnly response")
        return ids, prov


class CrimLookup:
    IDENTIFIER_FIELDS = {
        LookupMode.NUM_CATASTRO: "NUM_CATASTRO",
        LookupMode.OLDPID: "OLDPID",
        LookupMode.GLOBALID: "GLOBALID",
        LookupMode.OBJECTID: "OBJECTID",
    }

    def __init__(self, client: CrimClient | None = None):
        self.client = client or CrimClient()

    @staticmethod
    def _state_for_count(count: int) -> LookupState:
        if count == 0:
            return LookupState.VALID_ZERO_RESULT
        if count == 1:
            return LookupState.MATCH
        return LookupState.MULTIPLE_CANDIDATES

    @staticmethod
    def _identity(mode: LookupMode, count: int) -> IdentityState:
        if count != 1:
            return IdentityState.UNRESOLVED if count > 1 else IdentityState.CANDIDATE_NOT_IDENTITY
        if mode in {LookupMode.NUM_CATASTRO, LookupMode.GLOBALID}:
            return IdentityState.CERTIFIED
        if mode in {LookupMode.OLDPID, LookupMode.OBJECTID}:
            return IdentityState.PROVISIONAL
        return IdentityState.CANDIDATE_NOT_IDENTITY

    def identifier(self, mode: LookupMode, value: Any, *, return_geometry: bool = True) -> LookupResult:
        if mode not in self.IDENTIFIER_FIELDS:
            raise InvalidInputError(f"{mode} is not an identifier lookup mode")
        field = self.IDENTIFIER_FIELDS[mode]
        raw = normalize_identifier(value)
        if mode == LookupMode.OBJECTID:
            try:
                oid = int(raw)
            except ValueError as exc:
                raise InvalidInputError("OBJECTID must be an integer") from exc
            where = f"OBJECTID={oid}"
        else:
            where = f"{field}='{_escape_sql_literal(raw)}'"
        payload, prov = self.client.query({
            "where": where,
            "outFields": "*",
            "returnGeometry": str(return_geometry).lower(),
            "outSR": 4326 if return_geometry else None,
            "orderByFields": "OBJECTID",
        })
        features = payload.get("features") or []
        if not isinstance(features, list):
            raise SourceResponseError("features must be an array")
        return LookupResult(
            state=self._state_for_count(len(features)),
            mode=mode,
            match_count=len(features),
            candidates=features,
            provenance=[prov],
            identity_state=self._identity(mode, len(features)),
        )

    def point(self, lon: float, lat: float) -> LookupResult:
        lon_f, lat_f, warnings = validate_lon_lat(lon, lat)
        geometry = json.dumps({"x": lon_f, "y": lat_f}, separators=(",", ":"))
        payload, prov = self.client.query({
            "geometry": geometry,
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "orderByFields": "OBJECTID",
        })
        features = payload.get("features") or []
        if not isinstance(features, list):
            raise SourceResponseError("features must be an array")
        return LookupResult(
            state=self._state_for_count(len(features)),
            mode=LookupMode.POINT,
            match_count=len(features),
            candidates=features,
            warnings=warnings,
            provenance=[prov],
            identity_state=IdentityState.CANDIDATE_NOT_IDENTITY,
        )

    def bbox(self, xmin: float, ymin: float, xmax: float, ymax: float) -> LookupResult:
        vals = tuple(float(v) for v in (xmin, ymin, xmax, ymax))
        if vals[0] >= vals[2] or vals[1] >= vals[3]:
            raise InvalidInputError("bbox must satisfy xmin < xmax and ymin < ymax")
        for lon, lat in ((vals[0], vals[1]), (vals[2], vals[3])):
            validate_lon_lat(lon, lat)
        geometry = ",".join(str(v) for v in vals)
        payload, prov = self.client.query({
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "orderByFields": "OBJECTID",
        })
        features = payload.get("features") or []
        if not isinstance(features, list):
            raise SourceResponseError("features must be an array")
        if payload.get("exceededTransferLimit"):
            raise PaginationError("bbox query exceeded transfer limit; use complete_query")
        return LookupResult(
            self._state_for_count(len(features)),
            LookupMode.BBOX,
            len(features),
            features,
            provenance=[prov],
            identity_state=IdentityState.CANDIDATE_NOT_IDENTITY,
        )

    def complete_query(self, where: str = "1=1", *, chunk_size: int = 500, return_geometry: bool = True) -> LookupResult:
        """Retrieve a bounded complete query using OBJECTID chunking and arithmetic closure."""
        if chunk_size < 1 or chunk_size > 1000:
            raise InvalidInputError("chunk_size must be between 1 and 1000")
        expected, p_count = self.client.count(where)
        object_ids, p_ids = self.client.object_ids(where)
        if len(object_ids) != expected:
            raise PaginationError(f"count/object-id mismatch: count={expected} ids={len(object_ids)}")
        all_features: list[dict[str, Any]] = []
        provenance = [p_count, p_ids]
        for start in range(0, len(object_ids), chunk_size):
            chunk = object_ids[start : start + chunk_size]
            if not chunk:
                continue
            payload, prov = self.client.query({
                "objectIds": ",".join(str(x) for x in chunk),
                "outFields": "*",
                "returnGeometry": str(return_geometry).lower(),
                "outSR": 4326 if return_geometry else None,
                "orderByFields": "OBJECTID",
            })
            provenance.append(prov)
            if payload.get("exceededTransferLimit"):
                raise PaginationError("chunk response exceeded transfer limit")
            features = payload.get("features") or []
            if not isinstance(features, list):
                raise SourceResponseError("features must be an array")
            all_features.extend(features)
        seen: dict[int, dict[str, Any]] = {}
        for feature in all_features:
            attrs = feature.get("attributes") or {}
            oid = attrs.get("OBJECTID")
            if not isinstance(oid, int):
                raise PaginationError("retrieved feature missing integer OBJECTID")
            if oid in seen:
                raise PaginationError(f"duplicate OBJECTID across chunks: {oid}")
            seen[oid] = feature
        missing = sorted(set(object_ids) - set(seen))
        extra = sorted(set(seen) - set(object_ids))
        if missing or extra or len(seen) != expected:
            raise PaginationError(
                f"retrieval failed arithmetic closure: expected={expected} unique={len(seen)} "
                f"missing={missing[:10]} extra={extra[:10]}"
            )
        ordered = [seen[oid] for oid in object_ids]
        return LookupResult(
            self._state_for_count(len(ordered)),
            LookupMode.BBOX,
            len(ordered),
            ordered,
            provenance=provenance,
            identity_state=IdentityState.CANDIDATE_NOT_IDENTITY,
        )


def classify_tipo(feature: Mapping[str, Any]) -> str:
    attrs = feature.get("attributes") if isinstance(feature, Mapping) else None
    tipo = attrs.get("TIPO") if isinstance(attrs, Mapping) else None
    return {"P": "PARCEL", "V": "ROAD", "A": "WATER"}.get(tipo, "UNKNOWN")


def graph_node_for_feature(feature: Mapping[str, Any], source_manifest_sha256: str) -> dict[str, Any]:
    attrs = feature.get("attributes") if isinstance(feature, Mapping) else None
    if not isinstance(attrs, Mapping):
        raise InvalidInputError("feature attributes are required")
    tipo = classify_tipo(feature)
    gid = attrs.get("GLOBALID")
    stable_material = str(gid) if gid else canonical_json(dict(attrs)).decode("utf-8")
    internal_id = "CRIM-" + hashlib.sha256(stable_material.encode("utf-8")).hexdigest()[:24]
    return {
        "node_id": internal_id,
        "node_type": "CRIM_PARCEL" if tipo == "PARCEL" else "CRIM_SPATIAL_FEATURE",
        "source": "CRIM_SIGE_PARCELARIO",
        "globalid_raw": gid,
        "num_catastro_raw": attrs.get("NUM_CATASTRO"),
        "oldpid_raw": attrs.get("OLDPID"),
        "tipo_raw": attrs.get("TIPO"),
        "categoria_raw": attrs.get("CATEGORIA"),
        "feature_type": tipo,
        "source_manifest_sha256": source_manifest_sha256,
    }
