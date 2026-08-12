from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core import (
    SOURCE_SPECS,
    ImmutableSnapshotStore,
    certify_baselines,
    decide_refresh,
    fetch_bytes,
    geojson_feature_rows,
    nhd_query_params,
    nid_query_params,
    request_signature,
    schema_fingerprint,
    sciencebase_file_url,
    sha256_bytes,
    write_source_registry,
)

DEFAULT_RUNTIME_ROOT = Path("data/raw/pr_hydrography")
DEFAULT_MANIFEST_ROOT = Path("manifests/pr_hydrography/runtime")


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


def _snapshot_payload(
    source_id: str,
    payload: bytes,
    *,
    params: dict[str, Any],
    runtime_root: Path,
    manifest_root: Path,
    extension: str,
    schema_fp: str,
    source_update_date: str = "",
    refresh: bool = False,
) -> dict[str, Any]:
    spec = SOURCE_SPECS[source_id]
    previous_data = _load_latest(manifest_root, source_id)
    previous = None
    if previous_data:
        from .core import SnapshotRecord

        previous = SnapshotRecord(**previous_data)
    digest = sha256_bytes(payload)
    decision = decide_refresh(
        previous,
        remote_sha256=digest,
        remote_schema_fingerprint=schema_fp,
        source_update_date=source_update_date,
    )
    if refresh and decision.startswith("NO_CHANGE"):
        return {"source_id": source_id, "decision": decision, "snapshot": previous_data}
    if decision == "BLOCKED_SCHEMA_DRIFT":
        return {
            "source_id": source_id,
            "decision": decision,
            "previous_schema": previous.schema_fingerprint if previous else "",
            "remote_schema": schema_fp,
        }
    store = ImmutableSnapshotStore(runtime_root)
    sig = request_signature(source_id, "GET", params)
    record = store.write(
        spec,
        payload,
        request_sig=sig,
        schema_fp=schema_fp,
        source_update_date=source_update_date,
        parent_snapshot=previous.snapshot_id if previous else "",
        extension=extension,
    )
    _write_latest(manifest_root, record)
    return {"source_id": source_id, "decision": decision, "snapshot": asdict(record)}


def pull_tiger(runtime_root: Path, manifest_root: Path, refresh: bool) -> dict[str, Any]:
    spec = SOURCE_SPECS["TIGER_PR_BOUNDARY"]
    payload, headers = fetch_bytes(spec.endpoint)
    if not payload.startswith(b"PK\x03\x04"):
        raise RuntimeError("TIGER endpoint did not return a ZIP archive")
    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as zf:
        names = sorted(zf.namelist())
    schema_fp = sha256_bytes(json.dumps(names, separators=(",", ":")).encode())
    return _snapshot_payload(
        spec.source_id,
        payload,
        params={},
        runtime_root=runtime_root,
        manifest_root=manifest_root,
        extension=".zip",
        schema_fp=schema_fp,
        source_update_date=headers.get("Last-Modified", ""),
        refresh=refresh,
    )


def pull_nhd(runtime_root: Path, manifest_root: Path, refresh: bool) -> dict[str, Any]:
    spec = SOURCE_SPECS["USGS_NHD_WATERBODY"]
    pages: list[dict[str, Any]] = []
    all_features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = nhd_query_params(offset=offset)
        payload, _headers = fetch_bytes(spec.endpoint, params=params)
        page = json.loads(payload.decode("utf-8"))
        features = page.get("features", [])
        if not isinstance(features, list):
            raise RuntimeError("NHD response features is not a list")
        pages.append({"offset": offset, "payload_sha256": sha256_bytes(payload), "features": features})
        all_features.extend(features)
        if len(features) < 2000:
            break
        offset += len(features)
    rows = []
    for feature in all_features:
        row = dict(feature.get("properties") or {})
        row["__geometry__"] = feature.get("geometry")
        rows.append(row)
    bundle = {
        "source_id": spec.source_id,
        "query": nhd_query_params(offset=0),
        "pages": pages,
        "feature_count": len(all_features),
    }
    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
    return _snapshot_payload(
        spec.source_id,
        payload,
        params=nhd_query_params(offset=0),
        runtime_root=runtime_root,
        manifest_root=manifest_root,
        extension=".json",
        schema_fp=schema_fingerprint(rows),
        refresh=refresh,
    )


def pull_nid(runtime_root: Path, manifest_root: Path, refresh: bool) -> dict[str, Any]:
    spec = SOURCE_SPECS["USACE_NID_DAMS"]
    params = nid_query_params()
    payload, headers = fetch_bytes(spec.endpoint, params=params)
    rows = geojson_feature_rows(payload)
    return _snapshot_payload(
        spec.source_id,
        payload,
        params=params,
        runtime_root=runtime_root,
        manifest_root=manifest_root,
        extension=".geojson",
        schema_fp=schema_fingerprint(rows),
        source_update_date=headers.get("Last-Modified", ""),
        refresh=refresh,
    )


def pull_bathy(runtime_root: Path, manifest_root: Path, refresh: bool) -> dict[str, Any]:
    spec = SOURCE_SPECS["USGS_INLAND_BATHY_V4"]
    item_payload, headers = fetch_bytes(spec.endpoint)
    item = json.loads(item_payload.decode("utf-8"))
    file_url = sciencebase_file_url(item)
    payload, file_headers = fetch_bytes(file_url)
    if not payload.startswith(b"PK\x03\x04"):
        raise RuntimeError("ScienceBase canonical v4 file is not a ZIP archive")
    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as zf:
        names = sorted(zf.namelist())
    schema_fp = sha256_bytes(json.dumps(names, separators=(",", ":")).encode())
    return _snapshot_payload(
        spec.source_id,
        payload,
        params={"sciencebase_item": spec.endpoint, "resolved_file_url": file_url},
        runtime_root=runtime_root,
        manifest_root=manifest_root,
        extension=".zip",
        schema_fp=schema_fp,
        source_update_date=str(item.get("dates", headers.get("Last-Modified", ""))),
        refresh=refresh,
    )


PULLERS = {
    "tiger": pull_tiger,
    "nhd": pull_nhd,
    "nid": pull_nid,
    "inland-bathy": pull_bathy,
}


def _run_pull(args: argparse.Namespace, *, refresh: bool) -> int:
    runtime_root = Path(args.runtime_root)
    manifest_root = Path(args.manifest_root)
    sources = list(PULLERS) if args.source == "all" else [args.source]
    results = []
    for source in sources:
        results.append(PULLERS[source](runtime_root, manifest_root, refresh))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 2 if any(row.get("decision") == "BLOCKED_SCHEMA_DRIFT" for row in results) else 0


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(row) for row in data]
    if isinstance(data, dict) and "features" in data:
        return [dict(feature.get("properties") or {}) for feature in data["features"]]
    raise RuntimeError(f"unsupported JSON row container: {path}")


def _certify(args: argparse.Namespace) -> int:
    result = certify_baselines(
        nhd_rows=_load_json_rows(Path(args.nhd_rows)),
        nid_rows=_load_json_rows(Path(args.nid_rows)),
        v4_rows=_load_json_rows(Path(args.v4_rows)),
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spiderweb PR authoritative hydrography acquisition plane v0.1")
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    registry = sub.add_parser("write-source-registry")
    registry.add_argument("--output", default="manifests/pr_hydrography/source_registry.csv")

    for name in ("pull-source", "refresh-changed"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--source", choices=[*PULLERS, "all"], default="all")

    hydro = sub.add_parser("pull-hydrography")
    hydro.add_argument("--source", choices=[*PULLERS, "all"], default="all")

    certify = sub.add_parser("certify-snapshot")
    certify.add_argument("--nhd-rows", required=True)
    certify.add_argument("--nid-rows", required=True)
    certify.add_argument("--v4-rows", required=True)
    certify.add_argument("--output", default="manifests/pr_hydrography/runtime/baseline_certification.json")

    resolve = sub.add_parser("resolve-relationships")
    resolve.add_argument("--input", required=True, help="Reserved v0.1 contract input; relationship resolution is library-first")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "write-source-registry":
        print(write_source_registry(Path(args.output)))
        return 0
    if args.command in {"pull-source", "pull-hydrography"}:
        return _run_pull(args, refresh=False)
    if args.command == "refresh-changed":
        return _run_pull(args, refresh=True)
    if args.command == "certify-snapshot":
        return _certify(args)
    if args.command == "resolve-relationships":
        raise SystemExit("Use scripts.source_adapters.pr_hydrography.core select_candidates/rank_candidates in v0.1; file-contract resolver lands after baseline fixtures are certified")
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
