from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ADAPTER_VERSION = "pr_hydrography_v0_1"
PR_STATEFP = "72"
PR_DISCOVERY_BBOX = (-68.148751, 17.681518837698235, -65.01850795595038, 18.71801230358108)


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    authority: str
    universe: str
    endpoint: str
    mutable: bool
    refresh_policy: str
    evidence_tier: str
    adapter: str
    expected_content: str
    notes: str = ""


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    source_id: str
    adapter_version: str
    request_signature: str
    source_update_date: str
    sha256: str
    bytes: int
    schema_fingerprint: str
    acquired_utc: str
    parent_snapshot: str
    payload_path: str
    state: str


@dataclass(frozen=True)
class CandidateRelationship:
    source_a_id: str
    source_b_id: str
    evidence_class: str
    evidence_rank: int
    distance_m: float | None = None
    explicit_hard_binding: bool = False
    source_taxonomy: str = ""


SOURCE_SPECS: dict[str, SourceSpec] = {
    "TIGER_PR_BOUNDARY": SourceSpec(
        source_id="TIGER_PR_BOUNDARY",
        authority="U.S. Census Bureau",
        universe="JURISDICTION_BOUNDARY",
        endpoint="https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip",
        mutable=False,
        refresh_policy="PIN_BY_VINTAGE",
        evidence_tier="T1",
        adapter="tiger_pr_boundary",
        expected_content="zip",
        notes="Filter STATEFP=72 after extraction; the source archive remains immutable.",
    ),
    "USGS_NHD_WATERBODY": SourceSpec(
        source_id="USGS_NHD_WATERBODY",
        authority="U.S. Geological Survey",
        universe="NHD_WATERBODY_FEATURE",
        endpoint="https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/12/query",
        mutable=True,
        refresh_policy="PROBE_SERVICE_THEN_SNAPSHOT_IF_CHANGED",
        evidence_tier="T1",
        adapter="nhd_waterbody",
        expected_content="geojson",
        notes="Layer 12 Waterbody - Large Scale. FTYPE is source taxonomy, never reservoir identity.",
    ),
    "USACE_NID_DAMS": SourceSpec(
        source_id="USACE_NID_DAMS",
        authority="U.S. Army Corps of Engineers",
        universe="NID_DAM_ASSET",
        endpoint="https://geospatial.sec.usace.army.mil/dls/rest/services/NID/National_Inventory_of_Dams_Public_Service/FeatureServer/0/query",
        mutable=True,
        refresh_policy="PROBE_SERVICE_THEN_SNAPSHOT_IF_CHANGED",
        evidence_tier="T1",
        adapter="nid_dams",
        expected_content="geojson",
        notes="Query Puerto Rico records from the public FeatureServer and preserve raw attributes.",
    ),
    "USGS_INLAND_BATHY_V4": SourceSpec(
        source_id="USGS_INLAND_BATHY_V4",
        authority="U.S. Geological Survey",
        universe="USGS_BATHY_SURVEY_FOOTPRINT",
        endpoint="https://www.sciencebase.gov/catalog/item/5fce600bd34e30b912396ad0?format=json",
        mutable=True,
        refresh_policy="PROBE_SCIENCEBASE_ITEM_THEN_SNAPSHOT_IF_CHANGED",
        evidence_tier="T1",
        adapter="usgs_inland_bathy",
        expected_content="sciencebase-item-json",
        notes="Resolve the canonical version-4 GDB ZIP from ScienceBase item metadata; do not infer bytes from filenames.",
    ),
}


BASELINE_EXPECTATIONS = {
    "nhd_total": 3213,
    "nhd_ftype_390": 2560,
    "nhd_ftype_436": 653,
    "nid_pr": 36,
    "v4_pr": 6,
    "v4_nid_hard_bindings": 5,
}

EXPECTED_V4_HARD_BINDINGS = {
    "PR00003": "120013188",
    "PR00011": "120013183",
    "PR00013": "26379747",
    "PR00021": "26449070",
    "PR00023": "26376999",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_signature(source_id: str, method: str, params: Mapping[str, Any] | Sequence[tuple[str, Any]]) -> str:
    if isinstance(params, Mapping):
        ordered = sorted((str(k), _normalize_param(v)) for k, v in params.items())
    else:
        ordered = [(str(k), _normalize_param(v)) for k, v in params]
    return sha256_bytes(canonical_json({"source_id": source_id, "method": method.upper(), "params": ordered}).encode())


def _normalize_param(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_normalize_param(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def schema_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    fields: dict[str, set[str]] = {}
    for row in rows:
        for key, value in row.items():
            fields.setdefault(str(key), set()).add(_type_name(value))
    normalized = [(key, sorted(types)) for key, types in sorted(fields.items())]
    return sha256_bytes(canonical_json(normalized).encode())


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return type(value).__name__


def strict_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError("null boolean")
    token = str(value).strip().lower()
    if token in {"true", "t", "1", "yes", "y"}:
        return True
    if token in {"false", "f", "0", "no", "n"}:
        return False
    raise ValueError(f"unrecognized boolean representation: {value!r}")


def matching_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\u00c2\u00e2](?=[\u00a0\s])", " ", text).replace("\u00a0", " ")
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


def canonical_pid(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:-2] if re.fullmatch(r"[0-9]+\.0", text) else text


class ImmutableSnapshotStore:
    """Content-addressed, immutable local snapshot store.

    Raw bytes are intentionally runtime data; callers should point root at a git-ignored or external path.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def write(self, spec: SourceSpec, payload: bytes, *, request_sig: str, schema_fp: str, source_update_date: str = "", parent_snapshot: str = "", extension: str = ".payload") -> SnapshotRecord:
        digest = sha256_bytes(payload)
        stamp = utc_now().replace(":", "").replace("-", "")
        snapshot_id = f"{spec.source_id}__{stamp}__{digest[:16]}"
        directory = self.root / spec.source_id / snapshot_id
        if directory.exists():
            raise FileExistsError(f"snapshot already exists: {directory}")
        directory.mkdir(parents=True, exist_ok=False)
        payload_path = directory / f"payload{extension}"
        tmp_fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".payload-", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, payload_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        record = SnapshotRecord(
            snapshot_id=snapshot_id,
            source_id=spec.source_id,
            adapter_version=ADAPTER_VERSION,
            request_signature=request_sig,
            source_update_date=source_update_date,
            sha256=digest,
            bytes=len(payload),
            schema_fingerprint=schema_fp,
            acquired_utc=utc_now(),
            parent_snapshot=parent_snapshot,
            payload_path=str(payload_path),
            state="SNAPSHOT_CREATED",
        )
        (directory / "snapshot.json").write_text(json.dumps(asdict(record), indent=2) + "\n", encoding="utf-8")
        return record


def decide_refresh(previous: SnapshotRecord | None, *, remote_sha256: str = "", remote_schema_fingerprint: str = "", source_update_date: str = "") -> str:
    if previous is None:
        return "ACQUIRE_INITIAL_SNAPSHOT"
    if remote_schema_fingerprint and remote_schema_fingerprint != previous.schema_fingerprint:
        return "BLOCKED_SCHEMA_DRIFT"
    if remote_sha256 and remote_sha256 == previous.sha256:
        return "NO_CHANGE"
    if source_update_date and previous.source_update_date and source_update_date == previous.source_update_date and not remote_sha256:
        return "NO_CHANGE_METADATA"
    return "ACQUIRE_NEW_SNAPSHOT"


def fetch_bytes(url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, timeout: int = 120) -> tuple[bytes, Mapping[str, str]]:
    pairs: list[tuple[str, Any]]
    if params is None:
        pairs = []
    elif isinstance(params, Mapping):
        pairs = list(params.items())
    else:
        pairs = list(params)
    encoded = urlencode(pairs, doseq=True)
    final_url = url + (("&" if "?" in url else "?") + encoded if encoded else "")
    req = Request(final_url, headers={"User-Agent": "spiderweb-pr-hydrography/0.1"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - registry declares authoritative public endpoints
        return response.read(), dict(response.headers.items())


def nhd_query_params(offset: int = 0, count: int = 2000) -> dict[str, Any]:
    xmin, ymin, xmax, ymax = PR_DISCOVERY_BBOX
    return {
        "where": "FTYPE IN (390,436)",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,PERMANENT_IDENTIFIER,GNIS_NAME,FTYPE,FCODE,AREASQKM",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultOffset": str(offset),
        "resultRecordCount": str(count),
        "f": "geojson",
    }


def nid_query_params() -> dict[str, Any]:
    return {
        "where": "State='PR' OR NID_ID LIKE 'PR%'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }


def sciencebase_file_url(item_json: Mapping[str, Any], *, preferred_name: str = "USGS_InlandBathyResearch_Invent_v4.gdb.zip") -> str:
    matches: list[str] = []
    for file_row in item_json.get("files", []) or []:
        name = str(file_row.get("name", ""))
        url = str(file_row.get("downloadUri") or file_row.get("url") or "")
        if name == preferred_name and url:
            matches.append(url)
    if len(matches) != 1:
        raise RuntimeError(f"ScienceBase canonical file resolution expected 1 match, got {len(matches)}")
    return matches[0]


def geojson_feature_rows(payload: bytes) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    features = data.get("features", [])
    if not isinstance(features, list):
        raise RuntimeError("GeoJSON features is not a list")
    rows: list[dict[str, Any]] = []
    for feature in features:
        props = dict(feature.get("properties") or {})
        props["__geometry__"] = feature.get("geometry")
        rows.append(props)
    return rows


def certify_nhd_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pids = [canonical_pid(row.get("PERMANENT_IDENTIFIER")) for row in rows]
    duplicate_pids = len(pids) - len(set(pids))
    f390 = sum(1 for row in rows if int(row.get("FTYPE")) == 390)
    f436 = sum(1 for row in rows if int(row.get("FTYPE")) == 436)
    unexpected = [row.get("FTYPE") for row in rows if int(row.get("FTYPE")) not in {390, 436}]
    return {
        "rows": len(rows),
        "ftype_390": f390,
        "ftype_436": f436,
        "duplicate_pid": duplicate_pids,
        "unexpected_ftype": len(unexpected),
        "arithmetic_closure": f390 + f436 == len(rows),
        "schema_fingerprint": schema_fingerprint(rows),
    }


def _nid_id(row: Mapping[str, Any]) -> str:
    for key in ("NID ID", "NID_ID", "nid_id", "NIDID"):
        if key in row and row[key] is not None:
            return str(row[key]).strip()
    return ""


def _nid_state(row: Mapping[str, Any]) -> str:
    for key in ("State", "STATE", "state"):
        if key in row and row[key] is not None:
            return str(row[key]).strip()
    return ""


def certify_nid_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    prefix_ids = {_nid_id(row) for row in rows if _nid_id(row).startswith("PR")}
    state_ids = {_nid_id(row) for row in rows if _nid_state(row) == "PR"}
    all_ids = [_nid_id(row) for row in rows]
    return {
        "rows": len(rows),
        "unique_nid_ids": len(set(all_ids)),
        "prefix_state_set_equal": prefix_ids == state_ids,
        "prefix_count": len(prefix_ids),
        "state_count": len(state_ids),
        "schema_fingerprint": schema_fingerprint(rows),
    }


def certify_v4_rows(rows: Sequence[Mapping[str, Any]], hard_bindings: Mapping[str, str] = EXPECTED_V4_HARD_BINDINGS) -> dict[str, Any]:
    pr_rows = [row for row in rows if str(row.get("Feature", row.get("feature", ""))).rstrip().endswith(", PR")]
    binding_rows = [(nid, canonical_pid(pid)) for nid, pid in hard_bindings.items()]
    return {
        "pr_rows": len(pr_rows),
        "hard_bindings": len(binding_rows),
        "hard_binding_pairs_unique": len(set(binding_rows)) == len(binding_rows),
        "schema_fingerprint": schema_fingerprint(rows),
    }


def certify_baselines(*, nhd_rows: Sequence[Mapping[str, Any]], nid_rows: Sequence[Mapping[str, Any]], v4_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    nhd = certify_nhd_rows(nhd_rows)
    nid = certify_nid_rows(nid_rows)
    v4 = certify_v4_rows(v4_rows)
    observed = {
        "nhd_total": nhd["rows"],
        "nhd_ftype_390": nhd["ftype_390"],
        "nhd_ftype_436": nhd["ftype_436"],
        "nid_pr": nid["rows"],
        "v4_pr": v4["pr_rows"],
        "v4_nid_hard_bindings": v4["hard_bindings"],
    }
    gates = {
        "nhd_arithmetic_closure": nhd["arithmetic_closure"],
        "nhd_duplicate_pid_zero": nhd["duplicate_pid"] == 0,
        "nhd_unexpected_ftype_zero": nhd["unexpected_ftype"] == 0,
        "nid_unique_ids": nid["unique_nid_ids"] == nid["rows"],
        "nid_prefix_state_equal": nid["prefix_state_set_equal"],
        "v4_hard_binding_pairs_unique": v4["hard_binding_pairs_unique"],
        "frozen_expectations_match": observed == BASELINE_EXPECTATIONS,
    }
    return {"observed": observed, "expected": dict(BASELINE_EXPECTATIONS), "gates": gates, "pass": all(gates.values()), "nhd": nhd, "nid": nid, "v4": v4}


def select_candidates(discovery: Sequence[CandidateRelationship], explicit: Sequence[CandidateRelationship]) -> list[CandidateRelationship]:
    """Union discovery candidates with explicit higher-grade evidence.

    Deterministic ordering is only serialization behavior. It is never evidence.
    """
    by_key: dict[tuple[str, str], CandidateRelationship] = {}
    for candidate in list(discovery) + list(explicit):
        key = (candidate.source_a_id, candidate.source_b_id)
        incumbent = by_key.get(key)
        if incumbent is None or candidate.evidence_rank < incumbent.evidence_rank or candidate.explicit_hard_binding:
            by_key[key] = candidate
    return sorted(by_key.values(), key=lambda row: (row.evidence_rank, row.source_a_id, row.source_b_id))


def rank_candidates(candidates: Sequence[CandidateRelationship]) -> dict[str, Any]:
    if not candidates:
        return {"state": "NO_CANDIDATES", "winner": None, "top": []}
    top_rank = min(row.evidence_rank for row in candidates)
    top = [row for row in candidates if row.evidence_rank == top_rank]
    if len(top) > 1:
        return {"state": "TOP_EVIDENCE_TIE_REVIEW", "winner": None, "top": top}
    winner = top[0]
    if winner.evidence_class.startswith("DISTANCE_ONLY") and not winner.explicit_hard_binding:
        return {"state": "UNRESOLVED_PROXIMITY_ONLY", "winner": None, "top": top}
    return {"state": "PREFERRED_RELATIONSHIP_CANDIDATE", "winner": winner, "top": top}


def write_source_registry(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(SourceSpec.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for spec in SOURCE_SPECS.values():
            writer.writerow(asdict(spec))
    return path


def copy_snapshot_export(snapshot: SnapshotRecord, destination: Path) -> Path:
    """Export a snapshot only by explicit copy; never mutate canonical bytes."""
    source = Path(snapshot.payload_path)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copyfile(source, destination)
    if sha256_file(destination) != snapshot.sha256:
        destination.unlink(missing_ok=True)
        raise RuntimeError("snapshot export hash mismatch")
    return destination
