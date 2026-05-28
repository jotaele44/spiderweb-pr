"""
Round-trip smoke test for the spiderweb federation producer skeleton.

Builds a package from `exports/samples/`, validates it in test mode, and
prints OK on success. Used as the one-shot proof that the producer skeleton
is functional with zero external services.

Usage:
    python scripts/smoke_export.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_export_package import build_package  # noqa: E402
from scripts.validate_export import validate_package    # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="spiderweb_smoke_") as tmp:
        out_dir = Path(tmp) / "package"
        build_package(
            out_dir=out_dir,
            source_dir=REPO_ROOT / "exports" / "samples",
            producer_id="spiderweb-pr",
            producer_version="0.1.0",
            schema_version="1.0",
            mode="test",
            generated_at="2026-05-28T00:00:00+00:00",
        )
        report = validate_package(out_dir, mode="test")
        if report["status"] != "ok":
            print("FAILED:", report, file=sys.stderr)
            return 2

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
