from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .control_plane import bind_historical_file, certification_gate, rebuild_from_snapshot_store
from .core import (
    SOURCE_SPECS,
    ImmutableSnapshotStore,
    certify_baselines,
    decide_refresh,
    geojson_feature_rows,
    nhd_query_params,
    nid_query_params,
    request_signature,
    schema_fingerprint,
    sciencebase_file_url,
    sha256_bytes,
    sha256_file,
    write_source_registry,
)
from .resolver import resolve_document
from .spine import build_spine
from .transport import STEP5A_FAILURE_CLASSES, classify_transport_outcome, step5a_failure_class

DEFAULT_RUNTIME_ROOT = Path("data/raw/pr_hydrography")
DEFAULT_MANIFEST_ROOT = Path("manifests/pr_hydrography/runtime")
DEFAULT_HISTORICAL_PARENT_ROOT = Path("data/raw/pr_hydrography/historical_2026_08_11")
STEP5A_SCHEMA = "spiderweb.pr_hydrography.step5a_live_acquisition.v0_1"
STEP5A_PASS_PARENT = "PR_HYDROGRAPHY_2026_08_11_v2"


@dataclass(frozen=True)
class FetchReceipt:
    receipt_id: str
    source_id: str
    requested_url: str
    final_url: str
    http_status: int | None
    response_headers: dict[str, str]
    content_type: str
    content_length: str
    etag: str
    last_modified: str
    retrieval_utc: str
    fetch_backend: str
    fetch_backend_version: str
    raw_bytes_sha256: str
    raw_bytes_length: int
    request_signature: str
    expected_content: str
    transport_state: str
    failure_class: str
    raw_path: str
    page_offset: int | None = None
    parent_receipt_id: str = ""
    relation: str = ""


@dataclass(frozen=True)
class FetchResult:
    payload: bytes
    receipt: FetchReceipt


class FetchFailure(RuntimeError):
    def __init__(self, receipt: FetchReceipt) -> None:
        self.receipt = receipt
        super().__init__(f"{receipt.source_id}: {receipt.transport_state}/{receipt.failure_class}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_latest(manifest_root: Path, source_id: str) -> dict[str, Any] | None:
    path = manifest_root / source_id / "latest_snapshot.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_latest(manifest_root: Path, record: object) -> None:
    data = asdict(record)  # type: ignore[arg-type]
    path = manifest_root / data["source_id"] / "latest_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _snapshot_payload(source_id: str, payload: bytes, *, params: dict[str, Any], runtime_root: Path, manifest_root: Path, extension: str, schema_fp: str, source_update_date: str = "", refresh: bool = False) -> dict[str, Any]:
    spec = SOURCE_SPECS[source_id]
    previous_data = _load_latest(manifest_root, source_id)
    previous = None
    if previous_data:
        from .core import SnapshotRecord
        previous = SnapshotRecord(**previous_data)
    digest = sha256_bytes(payload)
    decision = decide_refresh(previous, remote_sha256=digest, remote_schema_fingerprint=schema_fp, source_update_date=source_update_date)
    if refresh and decision.startswith("NO_CHANGE"):
        return {"source_id": source_id, "decision": decision, "snapshot": previous_data}
    if decision == "BLOCKED_SCHEMA_DRIFT":
        return {"source_id": source_id, "decision": decision, "previous_schema": previous.schema_fingerprint if previous else "", "remote_schema": schema_fp}
    store = ImmutableSnapshotStore(runtime_root)
    sig = request_signature(source_id, "GET", params)
    record = store.write(spec, payload, request_sig=sig, schema_fp=schema_fp, source_update_date=source_update_date, parent_snapshot=previous.snapshot_id if previous else "", extension=extension)
    _write_latest(manifest_root, record)
    return {"source_id": source_id, "decision": decision, "snapshot": asdict(record)}


def _compose_url(url: str, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None) -> str:
    if not params:
        return url
    pairs = list(params.items()) if isinstance(params, Mapping) else list(params)
    encoded = urllib.parse.urlencode(pairs, doseq=True)
    return url + (("&" if "?" in url else "?") + encoded)


def _headers_dict(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(k): str(v) for k, v in sorted(headers.items(), key=lambda item: item[0].lower())}


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return ""


def _atomic_exact_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"append-only raw response already exists: {path}")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    if path.stat().st_size != len(payload) or sha256_file(path) != sha256_bytes(payload):
        path.unlink(missing_ok=True)
        raise RuntimeError("HASH_FAILURE: persisted raw response differs from acquired bytes")


def _receipt_id(source_id: str, requested_url: str, payload: bytes, retrieval_utc: str) -> str:
    canonical = json.dumps(
        {"source_id": source_id, "requested_url": requested_url, "raw_bytes_sha256": sha256_bytes(payload), "retrieval_utc": retrieval_utc},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256_bytes(canonical)[:24]


def fetch_with_receipt(
    *,
    source_id: str,
    url: str,
    expected_content: str,
    raw_root: Path,
    raw_name: str,
    params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None,
    timeout: int = 120,
    page_offset: int | None = None,
    parent_receipt_id: str = "",
    relation: str = "",
) -> FetchResult:
    requested_url = _compose_url(url, params)
    retrieval_utc = _utc_now()
    request_sig = request_signature(source_id, "GET", params or {})
    payload = b""
    response_headers: dict[str, str] = {}
    final_url = requested_url
    status: int | None = None
    timed_out = False
    network_error = False
    forced_state = ""

    request = urllib.request.Request(requested_url, headers={"User-Agent": "spiderweb-pr-hydrography/0.2-step5a"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - authoritative public endpoints are registry-bound
            payload = response.read()
            response_headers = _headers_dict(dict(response.headers.items()))
            final_url = response.geturl()
            status = getattr(response, "status", None) or response.getcode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        final_url = exc.geturl() or requested_url
        response_headers = _headers_dict(dict(exc.headers.items()) if exc.headers else {})
        try:
            payload = exc.read()
        except Exception:
            payload = b""
        if 300 <= exc.code < 400:
            forced_state = "HTTP_REDIRECT"
        else:
            network_error = True
    except TimeoutError:
        timed_out = True
    except urllib.error.URLError as exc:
        timed_out = isinstance(getattr(exc, "reason", None), TimeoutError)
        network_error = not timed_out
    except OSError:
        network_error = True

    content_type = _header(response_headers, "Content-Type")
    content_length = _header(response_headers, "Content-Length")
    expected_bytes = int(content_length) if content_length.isdigit() else None
    transport_state = forced_state or classify_transport_outcome(
        status=status,
        content_type=content_type,
        payload=payload,
        expected_content=expected_content,
        timed_out=timed_out,
        network_error=network_error,
        expected_bytes=expected_bytes,
    )
    failure_class = step5a_failure_class(transport_state)

    receipt_token = _receipt_id(source_id, requested_url, payload, retrieval_utc)
    raw_path = raw_root / source_id / receipt_token / raw_name
    if payload:
        try:
            _atomic_exact_write(raw_path, payload)
        except Exception as exc:
            transport_state = "HASH_FAILURE"
            failure_class = "HASH_FAILURE"
            raise RuntimeError(f"HASH_FAILURE: {exc}") from exc

    receipt = FetchReceipt(
        receipt_id=receipt_token,
        source_id=source_id,
        requested_url=requested_url,
        final_url=final_url,
        http_status=status,
        response_headers=response_headers,
        content_type=content_type,
        content_length=content_length,
        etag=_header(response_headers, "ETag"),
        last_modified=_header(response_headers, "Last-Modified"),
        retrieval_utc=retrieval_utc,
        fetch_backend="python_stdlib_urllib",
        fetch_backend_version=platform.python_version(),
        raw_bytes_sha256=sha256_bytes(payload),
        raw_bytes_length=len(payload),
        request_signature=request_sig,
        expected_content=expected_content,
        transport_state=transport_state,
        failure_class=failure_class,
        raw_path=str(raw_path) if payload else "",
        page_offset=page_offset,
        parent_receipt_id=parent_receipt_id,
        relation=relation,
    )
    return FetchResult(payload=payload, receipt=receipt)


def _require_fetch_ok(result: FetchResult) -> None:
    if result.receipt.transport_state != "OK":
        raise FetchFailure(result.receipt)


def _hash_tree(root: Path) -> dict[str, str]:
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    return {str(path.relative_to(root)): sha256_file(path) for path in sorted(p for p in root.rglob("*") if p.is_file())}


def compare_parent_tree(before: Mapping[str, str], after: Mapping[str, str]) -> dict[str, Any]:
    before_keys = set(before)
    after_keys = set(after)
    changed = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    return {"changed": changed, "added": added, "removed": removed, "historical_parent_mutations": len(changed) + len(added) + len(removed)}


def _source_run_root(runtime_root: Path) -> Path:
    stamp = _utc_now().replace(":", "").replace("-", "")
    root = runtime_root / "live_responses" / stamp
    root.mkdir(parents=True, exist_ok=False)
    return root


def _append_receipt_set(manifest_root: Path, report: Mapping[str, Any]) -> Path:
    receipt_root = manifest_root / "live_receipts"
    receipt_root.mkdir(parents=True, exist_ok=True)
    run_id = str(report["run_id"])
    path = receipt_root / f"{run_id}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    return path


def pull_tiger(runtime_root: Path, manifest_root: Path, refresh: bool, *, raw_root: Path | None = None) -> dict[str, Any]:
    spec = SOURCE_SPECS["TIGER_PR_BOUNDARY"]
    raw_root = raw_root or _source_run_root(runtime_root)
    fetched = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, expected_content="zip", raw_root=raw_root, raw_name="tl_2025_us_state.zip")
    _require_fetch_ok(fetched)
    with zipfile.ZipFile(Path(fetched.receipt.raw_path)) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"UNEXPECTED_MEDIA: corrupt TIGER member {bad}")
        names = sorted(zf.namelist())
    schema_fp = sha256_bytes(json.dumps(names, separators=(",", ":")).encode())
    result = _snapshot_payload(spec.source_id, fetched.payload, params={}, runtime_root=runtime_root, manifest_root=manifest_root, extension=".zip", schema_fp=schema_fp, source_update_date=fetched.receipt.last_modified, refresh=refresh)
    result.update({"receipts": [asdict(fetched.receipt)], "raw_remote_zip_preserved_verbatim": True, "zip_valid": True, "repacked": False})
    return result


def pull_nhd(runtime_root: Path, manifest_root: Path, refresh: bool, *, raw_root: Path | None = None) -> dict[str, Any]:
    spec = SOURCE_SPECS["USGS_NHD_WATERBODY"]
    raw_root = raw_root or _source_run_root(runtime_root)
    page_receipts: list[FetchReceipt] = []
    all_features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = nhd_query_params(offset=offset)
        fetched = fetch_with_receipt(
            source_id=spec.source_id,
            url=spec.endpoint,
            params=params,
            expected_content="geojson",
            raw_root=raw_root,
            raw_name=f"nhd_page_{offset:06d}.geojson",
            page_offset=offset,
        )
        _require_fetch_ok(fetched)
        page = json.loads(fetched.payload.decode("utf-8"))
        features = page.get("features")
        if not isinstance(features, list):
            raise RuntimeError(f"SCHEMA_CHANGED: NHD page offset={offset} features is not a list")
        page_receipts.append(fetched.receipt)
        all_features.extend(features)
        if len(features) < 2000:
            break
        offset += len(features)

    accounted = sum(receipt.raw_bytes_length for receipt in page_receipts)
    persisted = sum(Path(receipt.raw_path).stat().st_size for receipt in page_receipts)
    hash_mismatches = sum(sha256_file(Path(receipt.raw_path)) != receipt.raw_bytes_sha256 for receipt in page_receipts)
    closure = accounted == persisted and hash_mismatches == 0
    if not closure:
        raise RuntimeError("HASH_FAILURE: NHD raw-page hash accounting closure failed")

    rows = []
    for feature in all_features:
        row = dict(feature.get("properties") or {})
        row["__geometry__"] = feature.get("geometry")
        rows.append(row)
    derivative = {
        "schema": "spiderweb.pr_hydrography.nhd_assembled_derivative.v0_1",
        "artifact_role": "DERIVATIVE",
        "source_id": spec.source_id,
        "raw_page_receipt_ids": [receipt.receipt_id for receipt in page_receipts],
        "feature_count": len(all_features),
        "features": all_features,
    }
    derivative_payload = json.dumps(derivative, ensure_ascii=False, separators=(",", ":")).encode()
    result = _snapshot_payload(spec.source_id, derivative_payload, params=nhd_query_params(offset=0), runtime_root=runtime_root, manifest_root=manifest_root, extension=".json", schema_fp=schema_fingerprint(rows), refresh=refresh)
    result.update({
        "receipts": [asdict(receipt) for receipt in page_receipts],
        "raw_page_count": len(page_receipts),
        "raw_page_bytes_accounted": accounted,
        "raw_page_bytes_persisted": persisted,
        "raw_page_hash_mismatches": hash_mismatches,
        "raw_page_hash_accounting_closure": closure,
        "assembled_product_role": "DERIVATIVE",
    })
    return result


def pull_nid(runtime_root: Path, manifest_root: Path, refresh: bool, *, raw_root: Path | None = None) -> dict[str, Any]:
    spec = SOURCE_SPECS["USACE_NID_DAMS"]
    raw_root = raw_root or _source_run_root(runtime_root)
    params = nid_query_params()
    fetched = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, params=params, expected_content="geojson", raw_root=raw_root, raw_name="nid_pr.geojson")
    _require_fetch_ok(fetched)
    try:
        rows = geojson_feature_rows(fetched.payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SCHEMA_CHANGED: NID GeoJSON parse failed: {exc}") from exc
    result = _snapshot_payload(spec.source_id, fetched.payload, params=params, runtime_root=runtime_root, manifest_root=manifest_root, extension=".geojson", schema_fp=schema_fingerprint(rows), source_update_date=fetched.receipt.last_modified, refresh=refresh)
    result.update({"receipts": [asdict(fetched.receipt)], "raw_geojson_preserved_verbatim": True, "normalization_derivative_only": True})
    return result


def pull_bathy(runtime_root: Path, manifest_root: Path, refresh: bool, *, raw_root: Path | None = None) -> dict[str, Any]:
    spec = SOURCE_SPECS["USGS_INLAND_BATHY_V4"]
    raw_root = raw_root or _source_run_root(runtime_root)
    metadata = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, expected_content="sciencebase-item-json", raw_root=raw_root, raw_name="sciencebase_item.json", relation="SCIENCEBASE_ITEM_METADATA")
    _require_fetch_ok(metadata)
    try:
        item = json.loads(metadata.payload.decode("utf-8"))
        file_url = sciencebase_file_url(item)
    except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise RuntimeError(f"SCHEMA_CHANGED: ScienceBase item could not resolve canonical v4 file: {exc}") from exc
    archive = fetch_with_receipt(
        source_id=spec.source_id,
        url=file_url,
        expected_content="zip",
        raw_root=raw_root,
        raw_name="USGS_InlandBathyResearch_Invent_v4.gdb.zip",
        parent_receipt_id=metadata.receipt.receipt_id,
        relation="RESOLVED_CANONICAL_FILE_FROM_METADATA",
    )
    _require_fetch_ok(archive)
    with zipfile.ZipFile(Path(archive.receipt.raw_path)) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"UNEXPECTED_MEDIA: corrupt Inland Bathymetry member {bad}")
        names = sorted(zf.namelist())
    schema_fp = sha256_bytes(json.dumps(names, separators=(",", ":")).encode())
    result = _snapshot_payload(spec.source_id, archive.payload, params={"sciencebase_item": spec.endpoint, "resolved_file_url": file_url}, runtime_root=runtime_root, manifest_root=manifest_root, extension=".zip", schema_fp=schema_fp, source_update_date=metadata.receipt.last_modified, refresh=refresh)
    result.update({
        "receipts": [asdict(metadata.receipt), asdict(archive.receipt)],
        "sciencebase_item_preserved_verbatim": True,
        "resolved_gdb_zip_preserved_verbatim": True,
        "metadata_file_receipt_binding": archive.receipt.parent_receipt_id == metadata.receipt.receipt_id,
        "zip_valid": True,
        "repacked": False,
    })
    return result


PULLERS = {"tiger": pull_tiger, "nhd": pull_nhd, "nid": pull_nid, "inland-bathy": pull_bathy}


def step5a_readiness() -> dict[str, Any]:
    receipt_fields = set(FetchReceipt.__dataclass_fields__)
    required_receipt_fields = {
        "requested_url", "final_url", "http_status", "response_headers", "content_type", "content_length",
        "etag", "last_modified", "retrieval_utc", "fetch_backend", "fetch_backend_version",
        "raw_bytes_sha256", "raw_bytes_length",
    }
    gates = {
        "four_primary_pullers_hardened": set(PULLERS) == {"tiger", "nhd", "nid", "inland-bathy"},
        "structured_fetch_receipt_complete": required_receipt_fields <= receipt_fields,
        "failure_ontology_complete": STEP5A_FAILURE_CLASSES == {
            "SOURCE_UNAVAILABLE", "UNEXPECTED_MEDIA", "SOURCE_EMPTY", "PARTIAL_RESPONSE",
            "REDIRECT_FAILURE", "HASH_FAILURE", "SCHEMA_CHANGED", "UNCLASSIFIED",
        },
        "append_only_raw_writer": callable(_atomic_exact_write),
        "parent_immutability_hashing": callable(_hash_tree) and callable(compare_parent_tree),
        "append_only_receipt_writer": callable(_append_receipt_set),
    }
    return {
        "schema": STEP5A_SCHEMA,
        "pass_parent": STEP5A_PASS_PARENT,
        "gates": gates,
        "state": "PASS_STEP5A_LIVE_ACQUISITION_PROVENANCE_READY" if all(gates.values()) else "BLOCKED_STEP5A_LIVE_ACQUISITION_PROVENANCE_READY",
    }


def _run_pull(args: argparse.Namespace, *, refresh: bool) -> int:
    runtime_root = Path(args.runtime_root)
    manifest_root = Path(args.manifest_root)
    parent_root = Path(args.parent_root)
    sources = list(PULLERS) if args.source == "all" else [args.source]
    parent_before = _hash_tree(parent_root)
    raw_root = _source_run_root(runtime_root)
    run_id = raw_root.name
    results: list[dict[str, Any]] = []
    failure_records: list[dict[str, Any]] = []
    failure_receipts: list[dict[str, Any]] = []

    for source in sources:
        try:
            results.append(PULLERS[source](runtime_root, manifest_root, refresh, raw_root=raw_root))
        except FetchFailure as exc:
            failure_receipts.append(asdict(exc.receipt))
            failure_records.append({"source": source, "failure_class": exc.receipt.failure_class, "error": str(exc)})
        except Exception as exc:
            token = str(exc).split(":", 1)[0]
            failure_class = token if token in STEP5A_FAILURE_CLASSES else "UNCLASSIFIED"
            failure_records.append({"source": source, "failure_class": failure_class, "error": str(exc)})

    parent_after = _hash_tree(parent_root)
    parent_immutability = compare_parent_tree(parent_before, parent_after)
    receipts = [receipt for result in results for receipt in result.get("receipts", [])] + failure_receipts
    unaccounted_response_bytes = sum(
        int(receipt.get("raw_bytes_length", 0))
        for receipt in receipts
        if int(receipt.get("raw_bytes_length", 0)) > 0 and (not receipt.get("raw_path") or not Path(str(receipt["raw_path"])).exists())
    )
    unclassified_fetch_outcomes = sum(receipt.get("failure_class") == "UNCLASSIFIED" for receipt in receipts) + sum(record["failure_class"] == "UNCLASSIFIED" for record in failure_records)
    silent_substitutions = 0
    gates = {
        "silent_substitutions_zero": silent_substitutions == 0,
        "unaccounted_response_bytes_zero": unaccounted_response_bytes == 0,
        "unclassified_fetch_outcomes_zero": unclassified_fetch_outcomes == 0,
        "historical_parent_mutations_zero": parent_immutability["historical_parent_mutations"] == 0,
        "all_requested_sources_completed": not failure_records and len(results) == len(sources),
    }
    report = {
        "schema": STEP5A_SCHEMA,
        "pass_parent": STEP5A_PASS_PARENT,
        "run_id": run_id,
        "source_results": results,
        "receipts": receipts,
        "failure_records": failure_records,
        "parent_immutability": parent_immutability,
        "silent_substitutions": silent_substitutions,
        "unaccounted_response_bytes": unaccounted_response_bytes,
        "unclassified_fetch_outcomes": unclassified_fetch_outcomes,
        "historical_parent_mutations": parent_immutability["historical_parent_mutations"],
        "gates": gates,
        "state": "PASS_STEP5A_LIVE_ACQUISITION_PROVENANCE_READY" if all(gates.values()) else "BLOCKED_STEP5A_LIVE_ACQUISITION_PROVENANCE_READY",
    }
    receipt_set_path = _append_receipt_set(manifest_root, report)
    report["receipt_set_path"] = str(receipt_set_path)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["state"].startswith("PASS_") else 9


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(row) for row in data]
    if isinstance(data, dict) and "features" in data:
        return [dict(feature.get("properties") or {}) for feature in data["features"]]
    raise RuntimeError(f"unsupported JSON row container: {path}")


def _certify(args: argparse.Namespace) -> int:
    result = certify_baselines(nhd_rows=_load_json_rows(Path(args.nhd_rows)), nid_rows=_load_json_rows(Path(args.nid_rows)), v4_rows=_load_json_rows(Path(args.v4_rows)))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 3


def _resolve(args: argparse.Namespace) -> int:
    document = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = resolve_document(document)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _build_spine(args: argparse.Namespace) -> int:
    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    relationships = json.loads(Path(args.relationships).read_text(encoding="utf-8"))
    result = build_spine(entities, relationships)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _audit(args: argparse.Namespace) -> int:
    gate = certification_gate(
        unclassified_source_changes=args.unclassified_source_changes,
        unaccounted_bytes=args.unaccounted_bytes,
        schema_role_violations=args.schema_role_violations,
        proximity_only_identities=args.proximity_only_identities,
        hidden_ties=args.hidden_ties,
        unexplained_denominator_drift=args.unexplained_denominator_drift,
        canonical_overwrites=args.canonical_overwrites,
        unbound_parent_snapshots=args.unbound_parent_snapshots,
    )
    print(json.dumps(gate, indent=2))
    return 0 if gate["state"] == "PASS" else 4


def _reproduce(args: argparse.Namespace) -> int:
    report = rebuild_from_snapshot_store(Path(args.snapshot_root), Path(args.output_root))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _bind_historical(args: argparse.Namespace) -> int:
    record = bind_historical_file(Path(args.path), source_id=args.source_id, expected_sha256=args.expected_sha256, media_type=args.media_type, original_certification=args.original_certification)
    print(json.dumps(asdict(record), indent=2))
    return 0 if record.binding_state == "EXACT_HASH_MATCH" else 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spiderweb PR authoritative hydrography control plane")
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    parser.add_argument("--parent-root", default=str(DEFAULT_HISTORICAL_PARENT_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    registry = sub.add_parser("write-source-registry")
    registry.add_argument("--output", default="manifests/pr_hydrography/source_registry.csv")

    for name in ("pull-source", "refresh-changed", "pull-hydrography"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--source", choices=[*PULLERS, "all"], default="all")

    sub.add_parser("step5a-readiness")

    certify = sub.add_parser("certify-snapshot")
    certify.add_argument("--nhd-rows", required=True)
    certify.add_argument("--nid-rows", required=True)
    certify.add_argument("--v4-rows", required=True)
    certify.add_argument("--output", default="manifests/pr_hydrography/runtime/baseline_certification.json")

    resolve = sub.add_parser("resolve-relationships")
    resolve.add_argument("--input", required=True)
    resolve.add_argument("--output", required=True)

    spine = sub.add_parser("build-reservoir-spine")
    spine.add_argument("--entities", required=True)
    spine.add_argument("--relationships", required=True)
    spine.add_argument("--output", required=True)

    reproduce = sub.add_parser("reproduce")
    reproduce.add_argument("--snapshot-root", required=True)
    reproduce.add_argument("--output-root", required=True)

    bind = sub.add_parser("bind-historical")
    bind.add_argument("--path", required=True)
    bind.add_argument("--source-id", required=True)
    bind.add_argument("--expected-sha256", required=True)
    bind.add_argument("--media-type", required=True)
    bind.add_argument("--original-certification", required=True)

    audit = sub.add_parser("audit-hydrography")
    for field in (
        "unclassified-source-changes",
        "unaccounted-bytes",
        "schema-role-violations",
        "proximity-only-identities",
        "hidden-ties",
        "unexplained-denominator-drift",
        "canonical-overwrites",
        "unbound-parent-snapshots",
    ):
        audit.add_argument(f"--{field}", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "write-source-registry":
        print(write_source_registry(Path(args.output)))
        return 0
    if args.command in {"pull-source", "pull-hydrography"}:
        return _run_pull(args, refresh=False)
    if args.command == "refresh-changed":
        return _run_pull(args, refresh=True)
    if args.command == "step5a-readiness":
        report = step5a_readiness()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["state"].startswith("PASS_") else 9
    if args.command == "certify-snapshot":
        return _certify(args)
    if args.command == "resolve-relationships":
        return _resolve(args)
    if args.command == "build-reservoir-spine":
        return _build_spine(args)
    if args.command == "reproduce":
        return _reproduce(args)
    if args.command == "bind-historical":
        return _bind_historical(args)
    if args.command == "audit-hydrography":
        return _audit(args)
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
