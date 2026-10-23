"""Write an isolated test package using Spiderweb's canonical package writer."""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from federation.usgs_native_reference import build_native_streams  # noqa: E402
from scripts.federation_export import write_package  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["test", "production"], default="test")
    args = parser.parse_args()
    streams, audit = build_native_streams(
        args.input_manifest, args.source_root, mode=args.mode
    )
    if args.out.exists() and any(args.out.iterdir()):
        raise ValueError(
            "Output must be empty: preserve previous packages instead of overwriting"
        )
    when = max(
        (row["extracted_at"] for row in streams["sources"]),
        key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    manifest = write_package(streams, args.out, "test", when)
    audit["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    audit["producer_writer"] = "scripts/federation_export.py:write_package"
    (args.out / "usgs_export_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (args.out / "TERMINAL_READY.txt").write_text(
        "USGS documentary reference test export. Production and activation BLOCKED.\n"
        "From thehub-pr root: python -m hub validate-package "
        "/absolute/path/to/this/package\n"
        "Do not add this package to live aggregation. Native geometry stays "
        "in attributes; no canonical locations emitted.\n"
        "Timestamps describe source retrieval, not geological events. "
        "Domain confidence is unassessed.\n"
    )
    print(json.dumps(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
