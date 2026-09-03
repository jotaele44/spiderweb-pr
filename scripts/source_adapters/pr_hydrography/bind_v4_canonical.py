from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .core import sha256_file

EXPECTED_SHA256 = "40d77b8c8dc1a4487891167ca8403f7244396a0dbe0f54b32fc3fab718372bfb"
DEFAULT_RELATIVE = Path(
    "UNRESOLVED/5fce600bd34e30b912396ad0_U.S._Geological_Survey_Inland_Bathymetric_and_Topobathymetric_Survey_Inventory__version_4/USGS_InlandBathyResearch_Invent_v4.gdb.zip"
)


def bind(source_root: Path, historical_root: Path, *, source_path: Path | None = None) -> dict[str, object]:
    source_root = source_root.expanduser().resolve()
    historical_root = historical_root.expanduser().resolve()
    source = (source_path.expanduser().resolve() if source_path else source_root / DEFAULT_RELATIVE)
    if not source.is_file():
        raise FileNotFoundError(source)
    actual = sha256_file(source)
    if actual != EXPECTED_SHA256:
        raise RuntimeError(
            f"canonical V4 archive hash mismatch: expected={EXPECTED_SHA256} actual={actual} path={source}"
        )

    target_dir = historical_root / "USGS_INLAND_BATHY_V4"
    target = target_dir / source.name
    if target.exists():
        if sha256_file(target) != EXPECTED_SHA256:
            raise RuntimeError(f"existing V4 target has wrong hash: {target}")
        state = "PASS_ALREADY_BOUND"
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f".{target.name}.staging")
        if staging.exists():
            staging.unlink()
        shutil.copyfile(source, staging)
        if sha256_file(staging) != EXPECTED_SHA256:
            staging.unlink(missing_ok=True)
            raise RuntimeError("post-copy V4 staging hash mismatch")
        staging.replace(target)
        state = "PASS_CANONICAL_V4_BOUND"

    record = {
        "schema": "spiderweb.pr_hydrography.v4_canonical_binding.v0_1",
        "source_id": "USGS_INLAND_BATHY_V4",
        "source_universe": "USGS_BATHY_SURVEY_FOOTPRINT",
        "source_path": str(source),
        "bound_path": str(target),
        "bytes": target.stat().st_size,
        "expected_sha256": EXPECTED_SHA256,
        "actual_sha256": sha256_file(target),
        "binding_state": "EXACT_HASH_MATCH",
        "historical_bytes_reencoded": False,
        "canonical_history_superseded": False,
        "state": state,
    }
    (target_dir / "binding.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind canonical USGS Inland Bathymetry v4 archive")
    parser.add_argument("source_root", nargs="?", default="/Users/jotaele/Downloads/PR_RESERVOIR_DATA")
    parser.add_argument("--historical-root", default="data/raw/pr_hydrography/historical_2026_08_11")
    parser.add_argument("--source-path")
    args = parser.parse_args()
    result = bind(
        Path(args.source_root),
        Path(args.historical_root),
        source_path=Path(args.source_path) if args.source_path else None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
