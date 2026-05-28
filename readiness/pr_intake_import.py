"""
PR INTAKE IMPORT (cross-repo consumer)

Consumes the Contract-Sweeper PR-intake router's spiderweb-pr lane export
(`spiderweb_pr_derivatives.csv`) and normalizes it into a Spiderweb-native
intel-record layer with a zero-loss manifest and a review queue.

Producer boundary (read as-is, never mutated):
  Contract-Sweeper/scripts/route_pr_intake.py -> spiderweb_pr_derivatives.csv
See docs/contracts/PR_INTAKE_DERIVATIVE_HANDOFF.md for the contract.

Key facts about the on-disk CSV (enforced by the producer's csv writer):
  * every value is a string; SQL/JSON nulls are written as empty strings
  * `domains` and `output_tables` are JSON-encoded array strings
  * column order is alphabetized (we read by header name, so order is irrelevant)

The router derivative carries no coordinates, so records are non-spatial by
default; a GeoJSON feature is emitted only for rows that DO carry optional
`latitude`/`longitude` (forward-compatible — see the handoff doc's "Known
limitation").
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jsonschema import Draft7Validator

# ── Producer boundary ─────────────────────────────────────────────────────────

DERIVATIVES_FILENAME = "spiderweb_pr_derivatives.csv"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "pr_intake_derivative.schema.json"
SOURCE_LAYER = "pr_intake_spiderweb_export"

# Fields parsed from JSON-encoded array strings.
_JSON_ARRAY_FIELDS = ("domains", "output_tables")

# Provenance / payload fields carried straight through from the derivative.
_PASSTHROUGH_FIELDS = (
    "record_id", "source_item_id", "canonical_repo", "related_repo_record_id",
    "source_name", "source_url", "published_at", "discovered_at",
    "title", "summary_own_words", "final_status",
    "evidence_tier", "confidence_level",
    "source_hash", "content_hash", "dedupe_group_id",
)


def _safe_float(val: Any) -> Optional[float]:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


class PRIntakeImport:
    def __init__(self, input_dir: str, output_dir: str,
                 derivatives_filename: str = DERIVATIVES_FILENAME):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.derivatives_filename = derivatives_filename
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._validator = Draft7Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

    def run(self) -> Dict[str, Any]:
        rows, missing_files = self._load_rows()
        records: List[Dict[str, Any]] = []
        review: List[Dict[str, Any]] = []

        for row in rows:
            record, errors = self._normalize_row(row)
            if errors:
                review.append({
                    "source_item_id": row.get("source_item_id", ""),
                    "record_id": row.get("record_id", ""),
                    "errors": "; ".join(errors),
                })
            else:
                records.append(record)

        spatial = [r for r in records if r["latitude"] is not None and r["longitude"] is not None]
        status_counts: Dict[str, int] = {}
        for r in records:
            s = r.get("final_status") or ""
            status_counts[s] = status_counts.get(s, 0) + 1

        # Zero-loss invariant: every input row is either imported or queued for review.
        zero_loss_pass = len(records) + len(review) == len(rows)

        manifest = self._write_outputs(records, spatial, review, rows, missing_files,
                                       status_counts, zero_loss_pass)
        return manifest

    # ── Loader ────────────────────────────────────────────────────────────────

    def _load_rows(self) -> Tuple[List[Dict[str, str]], List[str]]:
        path = self.input_dir / self.derivatives_filename
        if not path.exists():
            return [], [self.derivatives_filename]
        with path.open("r", encoding="utf-8", newline="") as f:
            return [dict(r) for r in csv.DictReader(f)], []

    # ── Normalizer / validator ──────────────────────────────────────────────────

    def _normalize_row(self, row: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        errors = [self._format_error(e) for e in self._validator.iter_errors(row)]
        if errors:
            return None, errors

        record: Dict[str, Any] = {k: row.get(k, "") for k in _PASSTHROUGH_FIELDS}

        for field in _JSON_ARRAY_FIELDS:
            parsed, err = self._parse_json_array(row.get(field, ""), field)
            if err:
                errors.append(err)
            else:
                record[field] = parsed

        # `domains` must be a non-empty array (every routed derivative has >=1 domain).
        if not errors and not record.get("domains"):
            errors.append("domains parsed to an empty array")

        if errors:
            return None, errors

        record["source_layer"] = SOURCE_LAYER
        record["latitude"] = _safe_float(row.get("latitude"))
        record["longitude"] = _safe_float(row.get("longitude"))
        record["is_spatial"] = record["latitude"] is not None and record["longitude"] is not None
        return record, []

    @staticmethod
    def _parse_json_array(raw: str, field: str) -> Tuple[Optional[List[Any]], Optional[str]]:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None, f"{field} is not valid JSON: {raw!r}"
        if not isinstance(value, list):
            return None, f"{field} is not a JSON array: {raw!r}"
        return value, None

    @staticmethod
    def _format_error(err) -> str:
        loc = ".".join(str(p) for p in err.absolute_path) or "<row>"
        return f"{loc}: {err.message}"

    # ── Output writers ────────────────────────────────────────────────────────

    def _write_outputs(
        self,
        records: List[Dict[str, Any]],
        spatial: List[Dict[str, Any]],
        review: List[Dict[str, Any]],
        rows: List[Dict[str, str]],
        missing_files: List[str],
        status_counts: Dict[str, int],
        zero_loss_pass: bool,
    ) -> Dict[str, Any]:
        records_sorted = sorted(records, key=lambda r: r.get("record_id", ""))

        (self.output_dir / "pr_intake_records.json").write_text(
            json.dumps(
                {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "source_file": self.derivatives_filename,
                    "record_count": len(records_sorted),
                    "records": records_sorted,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
                "properties": {k: r[k] for k in _PASSTHROUGH_FIELDS + ("domains", "final_status")},
            }
            for r in sorted(spatial, key=lambda r: r.get("record_id", ""))
        ]
        (self.output_dir / "pr_intake_records.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
                    "features": features,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        review_path = self.output_dir / "pr_intake_review_queue.csv"
        with review_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["source_item_id", "record_id", "errors"])
            w.writeheader()
            w.writerows(review)

        manifest = {
            "schema_version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "export_dir": str(self.input_dir),
            "candidate_count": len(records_sorted),
            "record_count": len(records_sorted),
            "spatial_count": len(spatial),
            "review_count": len(review),
            "missing_files": missing_files,
            "dedup_removed": 0,
            "status_counts": status_counts,
            "zero_loss_pass": zero_loss_pass,
            "sources": [
                {
                    "source_file": self.derivatives_filename,
                    "records_loaded": len(rows),
                    "records_valid": len(records_sorted),
                    "parse_errors": len(review),
                }
            ],
            "notes": None if not missing_files else f"missing input: {missing_files}",
        }
        (self.output_dir / "pr_intake_import_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import the Contract-Sweeper PR-intake router spiderweb-pr lane "
                    "(spiderweb_pr_derivatives.csv) into a Spiderweb intel-record layer."
    )
    parser.add_argument("--input-dir", default="data/intake/pr_intake",
                        help="Directory containing spiderweb_pr_derivatives.csv (the dropzone).")
    parser.add_argument("--output-dir", default="data/intake/pr_intake",
                        help="Directory for normalized outputs (default: same as input).")
    parser.add_argument("--derivatives-file", default=DERIVATIVES_FILENAME,
                        help="Override the derivative CSV filename.")
    args = parser.parse_args(argv)

    manifest = PRIntakeImport(args.input_dir, args.output_dir, args.derivatives_file).run()
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest["zero_loss_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
