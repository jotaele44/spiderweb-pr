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
from typing import Any, Callable, Mapping, TypeGuard

LAYER_URL = "https://sigejp.pr.gov/server/rest/services/crim/crim_parcelas/MapServer/0"
QUERY_URL = f"{LAYER_URL}/query"
ADAPTER_VERSION = "0.1.0"
REQUIRED_FIELDS = {
    "OBJECTID",
    "GLOBALID",
    "NUM_CATASTRO",
    "OLDPID",
    "TIPO",
    "CATEGORIA",
}
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
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_exact_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def normalize_identifier(value: Any) -> str:
    if value is None or isinstance(value, bool):
        raise InvalidInputError("identifier is required")
    text = str(value).strip()
    if not text:
        raise InvalidInputError("identifier must not be empty")
    if len(text) > 256:
        raise InvalidInputError("identifier is unreasonably long")
    return text


def validate_lon_lat(lon: float, lat: float) -> tuple[float, float, list[str]]:
    if isinstance(lon, bool) or isinstance(lat, bool):
        raise InvalidInputError("longitude and latitude must be numeric")
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
    layer_id = metadata.get("id")
    if not _is_exact_int(layer_id) or layer_id != 0:
        raise SchemaDriftError(f"unexpected CRIM layer id: {metadata.get('id')!r}")
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise SchemaDriftError(
            f"unexpected geometry type: {metadata.get('geometryType')!r}"
        )
    raw_fields = metadata.get("fields")
    if not isinstance(raw_fields, list):
        raise SchemaDriftError("layer fields must be an array")
    field_names: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for field_def in raw_fields:
        if not isinstance(field_def, Mapping) or not isinstance(
            field_def.get("name"), str
        ):
            raise SchemaDriftError("every layer field must have a string name")
        name = field_def["name"]
        if name in seen:
            duplicates.add(name)
        seen.add(name)
        field_names.append(name)
    if duplicates:
        raise SchemaDriftError(
            f"duplicate field names: {', '.join(sorted(duplicates))}"
        )
    missing = sorted(REQUIRED_FIELDS - set(field_names))
    if missing:
        raise SchemaDriftError(f"required fields missing: {', '.join(missing)}")
    sr = metadata.get("sourceSpatialReference")
    if sr is None:
        extent = metadata.get("extent")
        sr = extent.get("spatialReference") if isinstance(extent, Mapping) else None
    if not isinstance(sr, Mapping):
        raise SchemaDriftError(f"missing native CRS: {sr!r}")
    crs_codes = (sr.get("wkid"), sr.get("latestWkid"))
    if not any(_is_exact_int(code) and code == 32161 for code in crs_codes):
        raise SchemaDriftError(f"unexpected native CRS: {sr!r}")


def _validated_features(
    payload: Mapping[str, Any], *, context: str
) -> list[dict[str, Any]]:
    if "features" not in payload:
        raise SourceResponseError(f"{context} response is missing features")
    features = payload["features"]
    if not isinstance(features, list):
        raise SourceResponseError(f"{context} response features must be an array")
    for feature in features:
        if not isinstance(feature, dict):
            raise SourceResponseError(
                f"{context} response features must contain objects"
            )
        attrs = feature.get("attributes")
        if not isinstance(attrs, Mapping):
            raise SourceResponseError(
                f"{context} response feature attributes must be an object"
            )
        if not _is_exact_int(attrs.get("OBJECTID")):
            raise SourceResponseError(
                f"{context} response feature requires an integer OBJECTID"
            )

    exceeded = payload.get("exceededTransferLimit", False)
    if not isinstance(exceeded, bool):
        raise SourceResponseError(
            f"{context} response exceededTransferLimit must be boolean"
        )
    if exceeded:
        raise PaginationError(f"{context} response exceeded transfer limit")
    return features


Transport = Callable[[str, Mapping[str, Any]], HttpResult]


class CrimClient:
    def __init__(
        self,
        transport: Transport | None = None,
        *,
        timeout: float = 30.0,
        retries: int = 2,
    ):
        self.timeout = timeout
        self.retries = retries
        self.transport = transport or self._http_get

    def _http_get(self, url: str, params: Mapping[str, Any]) -> HttpResult:
        encoded = urllib.parse.urlencode(
            [(k, str(v)) for k, v in params.items() if v is not None]
        )
        full_url = f"{url}?{encoded}"
        attempts: list[dict[str, Any]] = []
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                req = urllib.request.Request(
                    full_url, headers={"User-Agent": "Spiderweb-PR CRIM Lookup/0.1"}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    status = int(getattr(resp, "status", 200))
                    content_type = resp.headers.get("Content-Type", "")
                    attempts.append(
                        {
                            "attempt": attempt + 1,
                            "status": status,
                            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                        }
                    )
                    return HttpResult(
                        status, content_type, body, full_url, tuple(attempts)
                    )
            except urllib.error.HTTPError as exc:
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "status": exc.code,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    }
                )
                if exc.code not in RETRYABLE_HTTP or attempt >= self.retries:
                    raise SourceTransportError(
                        f"CRIM HTTP {exc.code} after {attempt + 1} attempt(s)"
                    ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "error": type(exc).__name__,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    }
                )
                if attempt >= self.retries:
                    raise SourceTransportError(
                        f"CRIM transport failure after {attempt + 1} attempt(s): {exc}"
                    ) from exc
            time.sleep(min(0.25 * (2**attempt), 2.0))
        raise AssertionError("unreachable")

    def _decode(
        self, result: HttpResult, params: Mapping[str, Any]
    ) -> tuple[dict[str, Any], Provenance]:
        request_identity = canonical_json(
            {"endpoint": result.url.split("?", 1)[0], "params": dict(params)}
        )
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
        if not _is_exact_int(count) or count < 0:
            raise SourceResponseError("count query returned invalid count")
        return count, prov

    def object_ids(self, where: str = "1=1") -> tuple[list[int], Provenance]:
        payload, prov = self.query({"where": where, "returnIdsOnly": "true"})
        if "objectIds" not in payload:
            raise SourceResponseError("object id query response is missing objectIds")
        ids = payload["objectIds"]
        if ids is None:
            ids = []
        if not isinstance(ids, list) or any(not _is_exact_int(value) for value in ids):
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
            return (
                IdentityState.UNRESOLVED
                if count > 1
                else IdentityState.CANDIDATE_NOT_IDENTITY
            )
        if mode in CrimLookup.IDENTIFIER_FIELDS:
            return IdentityState.PROVISIONAL
        return IdentityState.CANDIDATE_NOT_IDENTITY

    def identifier(
        self, mode: LookupMode, value: Any, *, return_geometry: bool = True
    ) -> LookupResult:
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
        payload, prov = self.client.query(
            {
                "where": where,
                "outFields": "*",
                "returnGeometry": str(return_geometry).lower(),
                "outSR": 4326 if return_geometry else None,
                "orderByFields": "OBJECTID",
            }
        )
        features = _validated_features(
            payload, context=f"{mode.value} identifier query"
        )
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
        payload, prov = self.client.query(
            {
                "geometry": geometry,
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "orderByFields": "OBJECTID",
            }
        )
        features = _validated_features(payload, context="point query")
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
        if any(isinstance(value, bool) for value in (xmin, ymin, xmax, ymax)):
            raise InvalidInputError("bbox coordinates must be numeric")
        try:
            vals = tuple(float(value) for value in (xmin, ymin, xmax, ymax))
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("bbox coordinates must be numeric") from exc
        if vals[0] >= vals[2] or vals[1] >= vals[3]:
            raise InvalidInputError("bbox must satisfy xmin < xmax and ymin < ymax")
        for lon, lat in ((vals[0], vals[1]), (vals[2], vals[3])):
            validate_lon_lat(lon, lat)
        geometry = ",".join(str(v) for v in vals)
        payload, prov = self.client.query(
            {
                "geometry": geometry,
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "orderByFields": "OBJECTID",
            }
        )
        features = _validated_features(payload, context="bbox query")
        return LookupResult(
            self._state_for_count(len(features)),
            LookupMode.BBOX,
            len(features),
            features,
            provenance=[prov],
            identity_state=IdentityState.CANDIDATE_NOT_IDENTITY,
        )

    def complete_query(
        self, where: str = "1=1", *, chunk_size: int = 500, return_geometry: bool = True
    ) -> LookupResult:
        """Retrieve a bounded complete query.

        OBJECTID chunking and arithmetic closure prevent partial certification.
        """
        if not isinstance(where, str) or not where.strip():
            raise InvalidInputError("where must be a non-empty string")
        if not _is_exact_int(chunk_size) or chunk_size < 1 or chunk_size > 1000:
            raise InvalidInputError("chunk_size must be between 1 and 1000")
        expected, p_count = self.client.count(where)
        object_ids, p_ids = self.client.object_ids(where)
        if len(object_ids) != expected:
            raise PaginationError(
                f"count/object-id mismatch: count={expected} ids={len(object_ids)}"
            )
        all_features: list[dict[str, Any]] = []
        provenance = [p_count, p_ids]
        for start in range(0, len(object_ids), chunk_size):
            chunk = object_ids[start : start + chunk_size]
            if not chunk:
                continue
            payload, prov = self.client.query(
                {
                    "objectIds": ",".join(str(x) for x in chunk),
                    "outFields": "*",
                    "returnGeometry": str(return_geometry).lower(),
                    "outSR": 4326 if return_geometry else None,
                    "orderByFields": "OBJECTID",
                }
            )
            provenance.append(prov)
            features = _validated_features(payload, context="complete-query chunk")
            all_features.extend(features)
        seen: dict[int, dict[str, Any]] = {}
        for feature in all_features:
            attrs = feature.get("attributes") or {}
            oid = attrs.get("OBJECTID")
            if not _is_exact_int(oid):
                raise PaginationError("retrieved feature missing integer OBJECTID")
            if oid in seen:
                raise PaginationError(f"duplicate OBJECTID across chunks: {oid}")
            seen[oid] = feature
        missing = sorted(set(object_ids) - set(seen))
        extra = sorted(set(seen) - set(object_ids))
        if missing or extra or len(seen) != expected:
            raise PaginationError(
                f"retrieval failed arithmetic closure: expected={expected} "
                f"unique={len(seen)} "
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
    if not isinstance(tipo, str):
        return "UNKNOWN"
    return {"P": "PARCEL", "V": "ROAD", "A": "WATER"}.get(tipo, "UNKNOWN")


def graph_node_for_feature(
    feature: Mapping[str, Any], source_manifest_sha256: str
) -> dict[str, Any]:
    attrs = feature.get("attributes") if isinstance(feature, Mapping) else None
    if not isinstance(attrs, Mapping):
        raise InvalidInputError("feature attributes are required")
    if (
        not isinstance(source_manifest_sha256, str)
        or len(source_manifest_sha256) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in source_manifest_sha256)
    ):
        raise InvalidInputError(
            "source manifest SHA-256 must be 64 hexadecimal characters"
        )
    oid = attrs.get("OBJECTID")
    if not _is_exact_int(oid):
        raise InvalidInputError("feature attributes require an integer OBJECTID")
    manifest_sha = source_manifest_sha256.lower()
    tipo = classify_tipo(feature)
    gid = attrs.get("GLOBALID")
    stable_material = canonical_json(
        {
            "source": "CRIM_SIGE_PARCELARIO",
            "source_manifest_sha256": manifest_sha,
            "objectid": oid,
        }
    )
    internal_id = "CRIM-" + hashlib.sha256(stable_material).hexdigest()[:24]
    return {
        "node_id": internal_id,
        "node_type": "CRIM_PARCEL" if tipo == "PARCEL" else "CRIM_SPATIAL_FEATURE",
        "source": "CRIM_SIGE_PARCELARIO",
        "objectid_raw": oid,
        "globalid_raw": gid,
        "num_catastro_raw": attrs.get("NUM_CATASTRO"),
        "oldpid_raw": attrs.get("OLDPID"),
        "tipo_raw": attrs.get("TIPO"),
        "categoria_raw": attrs.get("CATEGORIA"),
        "feature_type": tipo,
        "source_manifest_sha256": manifest_sha,
    }
