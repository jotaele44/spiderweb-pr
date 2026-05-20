"""
SATELLITE INGEST
Validates and ingests satellite source manifests into the data pipeline.

Reads a satellite_source_manifest JSON file, validates against the contract
schema, verifies the asset checksum (when local_path is present), checks bbox
overlap with the active PR region, and writes validated manifests to
data/satellite_manifests/.

Usage (CLI):
    python run_all.py --ingest-satellite MANIFEST_PATH [--dry-run]
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMAS_DIR = Path(__file__).parent / "schemas"
MANIFEST_SCHEMA_NAME = "satellite_source_manifest"
SATELLITE_MANIFESTS_DIR = Path(__file__).parent / "data" / "satellite_manifests"

# Puerto Rico bounding box (loose envelope matching schema definitions)
PR_LON_MIN, PR_LON_MAX = -68.2, -65.1
PR_LAT_MIN, PR_LAT_MAX = 17.8, 18.7


class SatelliteIngestError(Exception):
    pass


class SatelliteIngest:
    """
    Validates and persists a satellite source manifest.

    Args:
        output_dir: Directory to write accepted manifests into.
                    Defaults to data/satellite_manifests/.
        dry_run:    If True, validate only — do not write to disk.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.output_dir = Path(output_dir) if output_dir else SATELLITE_MANIFESTS_DIR
        self.dry_run = dry_run
        self._validator = self._load_validator()

    # ── public ────────────────────────────────────────────────────────────────

    def ingest(self, manifest_path: str) -> Dict[str, Any]:
        """
        Load, validate, and (unless dry_run) persist a manifest.

        Returns a result dict with keys:
          status   : "accepted" | "rejected"
          errors   : list[str]
          manifest : the loaded manifest dict (or None on parse failure)
          output_path : path written (if accepted and not dry_run), else None
        """
        result: Dict[str, Any] = {
            "status": "rejected",
            "errors": [],
            "manifest": None,
            "output_path": None,
        }

        manifest = self._load_json(manifest_path, result)
        if manifest is None:
            return result
        result["manifest"] = manifest

        errors = []
        errors += self._validate_schema(manifest)
        errors += self._check_fixture_mode(manifest)
        errors += self._check_bbox_overlap(manifest)
        errors += self._verify_checksum(manifest)

        if errors:
            result["errors"] = errors
            return result

        result["status"] = "accepted"

        self._attach_terrain_stats(manifest)

        if not self.dry_run:
            out_path = self._write_manifest(manifest, manifest_path)
            result["output_path"] = out_path

        return result

    # ── internal ──────────────────────────────────────────────────────────────

    def _load_json(self, path: str, result: Dict) -> Optional[Dict]:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            result["errors"].append(f"File not found: {path}")
            return None
        except json.JSONDecodeError as e:
            result["errors"].append(f"JSON parse error: {e}")
            return None

    def _validate_schema(self, manifest: Dict) -> list:
        if self._validator is None:
            return []
        result = self._validator.validate(manifest, MANIFEST_SCHEMA_NAME)
        return result["errors"]

    def _check_fixture_mode(self, manifest: Dict) -> list:
        """Block fixture/test/mock asset URIs on non-synthetic manifests."""
        if manifest.get("synthetic") is True:
            return []
        asset = manifest.get("asset", {})
        errors = []
        for field in ("source_uri", "local_path"):
            val = asset.get(field, "")
            if val and any(tok in val.lower() for tok in ("fixture", "test", "mock")):
                errors.append(
                    f"asset.{field} contains fixture/test/mock marker "
                    f"but synthetic=false: {val!r}"
                )
        return errors

    def _check_bbox_overlap(self, manifest: Dict) -> list:
        bbox = manifest.get("geometry", {}).get("bbox")
        if not bbox or len(bbox) < 4:
            return []
        west, south, east, north = bbox[:4]
        if (east < PR_LON_MIN or west > PR_LON_MAX or
                north < PR_LAT_MIN or south > PR_LAT_MAX):
            return [
                f"bbox {bbox} does not overlap PR region "
                f"([{PR_LON_MIN},{PR_LAT_MIN},{PR_LON_MAX},{PR_LAT_MAX}])"
            ]
        return []

    def _verify_checksum(self, manifest: Dict) -> list:
        local_path = manifest.get("asset", {}).get("local_path")
        expected = manifest.get("asset", {}).get("checksum_sha256")
        if not local_path or not expected:
            return []
        p = Path(local_path)
        if not p.exists():
            return []
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != expected:
            return [
                f"checksum mismatch for {local_path}: "
                f"expected {expected}, got {actual}"
            ]
        return []

    def _write_manifest(self, manifest: Dict, source_path: str) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(source_path).stem
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out = self.output_dir / f"{ts}_{stem}.json"
        out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return str(out)

    def _attach_terrain_stats(self, manifest: Dict) -> None:
        """Optionally populate manifest['terrain'] with elevation stats from GEBCO.

        Silently skips if GEBCO data is unavailable or bbox is absent.
        Stats are pre-computed here for informational purposes only — they do
        not affect accept/reject status.
        """
        if "terrain" in manifest:
            return
        bbox = manifest.get("geometry", {}).get("bbox")
        if not bbox or len(bbox) < 4:
            return
        try:
            from gebco import open_gebco
            west, south, east, north = bbox[:4]
            ds = open_gebco(west=west, south=south, east=east, north=north)
            elev = ds["elevation"].values.astype(float)
            manifest["terrain"] = {
                "min_elevation_m":  float(elev.min()),
                "max_elevation_m":  float(elev.max()),
                "mean_elevation_m": float(elev.mean()),
                "std_elevation_m":  float(elev.std()),
                "data_source": "gebco-2023",
            }
        except Exception:
            pass

    def ingest_batch(self, manifest_paths) -> list:
        """Ingest multiple manifests; return list of per-manifest result dicts."""
        return [self.ingest(str(p)) for p in manifest_paths]

    @staticmethod
    def get_ingest_summary(results: list) -> Dict[str, Any]:
        """Compute acceptance stats from a list of ingest() result dicts."""
        total    = len(results)
        accepted = sum(1 for r in results if r.get("status") == "accepted")
        rejected = total - accepted
        return {
            "total":           total,
            "accepted":        accepted,
            "rejected":        rejected,
            "acceptance_rate": round(accepted / total, 4) if total else 0.0,
        }

    def _load_validator(self):
        try:
            from schema_validation import SchemaValidator
            return SchemaValidator()
        except Exception:
            return None


def ingest_from_cli(manifest_path: str, dry_run: bool = False) -> int:
    """Entry point for run_all.py --ingest-satellite. Returns exit code."""
    ingester = SatelliteIngest(dry_run=dry_run)
    result = ingester.ingest(manifest_path)

    if result["status"] == "accepted":
        note = " (dry-run)" if dry_run else f" → {result['output_path']}"
        print(f"  ✓ Manifest accepted{note}")
        return 0
    else:
        print(f"  ✗ Manifest rejected:")
        for err in result["errors"]:
            print(f"    - {err}")
        return 1
