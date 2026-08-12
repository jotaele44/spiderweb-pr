from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from .certifiers import certify_nid_csv
from .core import EXPECTED_V4_HARD_BINDINGS, sha256_file

EXPECTED = {
    "nhd": "08a216d247a1ed7a59046d94a4a8f858ffbd9e9164175ce8927ccd8e791cc45a",
    "nid": "67890b6bc0eca8976fa646080bc527a619b8729166dcf7bf7ec694db1bb3f82e",
    "v4": "40d77b8c8dc1a4487891167ca8403f7244396a0dbe0f54b32fc3fab718372bfb",
    "v4_crosswalk": "747dcdda28535f83074aa486bdb01411e291f43733da8729cf418e62307a9a45",
    "tiger": "59a220888a8d9be8117c4fcd38f542bd02d81abf0d198c78113595ad540dd957",
}


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"required source missing: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch: {path} expected={expected} actual={actual}")


def _read_vector(path: Path, layer: str | None = None):
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError("geopandas is required for historical source certification; install spiderweb-pr[geo]") from exc
    return gpd.read_file(path, layer=layer)


def _certify_tiger(path: Path) -> dict[str, Any]:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(td)
        shp = next(Path(td).glob("*.shp"), None)
        if shp is None:
            raise RuntimeError("TIGER archive contains no shapefile")
        gdf = _read_vector(shp)
    if "STATEFP" not in gdf.columns:
        raise RuntimeError("TIGER STATEFP column missing")
    pr = gdf[gdf["STATEFP"].astype(str).str.zfill(2) == "72"]
    if len(pr) != 1:
        raise RuntimeError(f"TIGER expected one PR row; got {len(pr)}")
    geom = pr.geometry.iloc[0]
    return {
        "statefp": "72",
        "rows_total": int(len(gdf)),
        "pr_rows": 1,
        "pr_geometry_valid": bool(geom.is_valid),
        "pr_geometry_empty": bool(geom.is_empty),
        "pr_bounds": [float(v) for v in geom.bounds],
        "crs": str(gdf.crs),
        "gate": "PASS",
    }


def _certify_nhd(path: Path) -> dict[str, Any]:
    gdf = _read_vector(path)
    required = {"PERMANENT_IDENTIFIER", "FTYPE", "FCODE"}
    missing = sorted(required - set(gdf.columns))
    if missing:
        raise RuntimeError(f"NHD required columns missing: {missing}")
    pids = gdf["PERMANENT_IDENTIFIER"].astype(str)
    ftype = gdf["FTYPE"].astype(int)
    f390 = int((ftype == 390).sum())
    f436 = int((ftype == 436).sum())
    unexpected = sorted(set(int(v) for v in ftype if int(v) not in {390, 436}))
    valid = gdf.geometry.is_valid
    empty = gdf.geometry.is_empty
    nulls = gdf.geometry.isna()
    return {
        "rows": int(len(gdf)),
        "ftype_390": f390,
        "ftype_436": f436,
        "duplicate_pid": int(pids.duplicated().sum()),
        "unexpected_ftype": unexpected,
        "null_geometry": int(nulls.sum()),
        "empty_geometry": int(empty.sum()),
        "invalid_source_geometry": int((~valid & ~nulls).sum()),
        "arithmetic_closure": f390 + f436 == len(gdf),
        "crs": str(gdf.crs),
        "gate": "PASS" if len(gdf) == 3213 and f390 == 2560 and f436 == 653 and pids.duplicated().sum() == 0 and not unexpected else "BLOCKED",
    }


def _certify_nid(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    cert = certify_nid_csv(payload)
    # The historical frozen source is the national CSV; certify the PR subset independently.
    text = payload.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header = cert["header_line_index"]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[header:]))))
    def nid(row: dict[str, str]) -> str:
        return str(row.get("NID ID") or row.get("NID_ID") or "").strip()
    def state(row: dict[str, str]) -> str:
        return str(row.get("State") or row.get("STATE") or "").strip()
    pr_prefix = [row for row in rows if nid(row).startswith("PR")]
    pr_state = [row for row in rows if state(row) == "PR"]
    prefix_ids = [nid(row) for row in pr_prefix]
    state_ids = [nid(row) for row in pr_state]
    return {
        **cert,
        "pr_prefix_rows": len(pr_prefix),
        "pr_state_rows": len(pr_state),
        "pr_unique_ids": len(set(prefix_ids)),
        "prefix_state_exact_set_equal": set(prefix_ids) == set(state_ids),
        "gate": "PASS" if len(pr_prefix) == 36 and len(pr_state) == 36 and len(set(prefix_ids)) == 36 and set(prefix_ids) == set(state_ids) else "BLOCKED",
    }


def _certify_v4(path: Path, crosswalk: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.infolist()]
        files = [m for m in members if not m.is_dir()]
        total_member_bytes = sum(m.file_size for m in files)
        names = sorted(m.filename for m in members)
    # Crosswalk is the frozen historical proof of six PR survey subjects and five NID hard bindings.
    rows = list(csv.DictReader(io.StringIO(crosswalk.read_text(encoding="utf-8"))))
    if len(rows) != 6:
        raise RuntimeError(f"V4 crosswalk expected six PR survey rows; got {len(rows)}")
    observed_pids = {str(row.get("nhd_permanent_identifier") or row.get("PERMANENT_IDENTIFIER") or row.get("nhd_pid") or "").strip() for row in rows}
    expected_pids = set(EXPECTED_V4_HARD_BINDINGS.values())
    hard_covered = len(expected_pids & observed_pids)
    return {
        "archive_member_count": len(members),
        "archive_file_count": len(files),
        "archive_member_uncompressed_bytes": total_member_bytes,
        "contains_gdb": any(".gdb/" in name or ".gdb\\" in name for name in names),
        "pr_crosswalk_rows": len(rows),
        "expected_hard_bindings": len(expected_pids),
        "hard_binding_pids_covered": hard_covered,
        "gate": "PASS" if len(rows) == 6 and hard_covered == 5 and any(".gdb/" in name or ".gdb\\" in name for name in names) else "BLOCKED",
    }


def certify(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    paths = {
        "nhd": root / "USGS_NHD_WATERBODY/nhd_pr_lakepond_reservoir.gpkg",
        "nid": root / "USACE_NID_DAMS/nid_nation.csv",
        "v4": root / "USGS_INLAND_BATHY_V4/USGS_InlandBathyResearch_Invent_v4.gdb.zip",
        "v4_crosswalk": root / "USGS_INLAND_BATHY_V4_CROSSWALK/v4_to_nhd_spatial_crosswalk.csv",
        "tiger": root / "TIGER_PR_BOUNDARY/tl_2025_us_state.zip",
    }
    for key, path in paths.items():
        _require_hash(path, EXPECTED[key])

    document = {
        "schema": "spiderweb.pr_hydrography.historical_source_certification.v0_1",
        "snapshot_set_id": "PR_HYDROGRAPHY_2026_08_11_v2",
        "tiger": _certify_tiger(paths["tiger"]),
        "nhd": _certify_nhd(paths["nhd"]),
        "nid": _certify_nid(paths["nid"]),
        "v4": _certify_v4(paths["v4"], paths["v4_crosswalk"]),
        "raw_source_hashes_verified": True,
        "selection_logic_used_frozen_counts": False,
    }
    gates = {name: document[name]["gate"] for name in ("tiger", "nhd", "nid", "v4")}
    document["gates"] = gates
    document["state"] = "PASS_HISTORICAL_SOURCE_SPECIFIC_CERTIFICATION" if all(v == "PASS" for v in gates.values()) else "BLOCKED_HISTORICAL_SOURCE_SPECIFIC_CERTIFICATION"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Run source-specific certifiers against frozen 2026-08-11 hydrography bytes")
    parser.add_argument("--root", default="data/raw/pr_hydrography/historical_2026_08_11")
    parser.add_argument("--output", default="manifests/pr_hydrography/runtime/historical_source_certification_2026_08_11.json")
    args = parser.parse_args()
    result = certify(Path(args.root), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["state"].startswith("PASS_") else 7


if __name__ == "__main__":
    raise SystemExit(main())
