"""
Federation export contract — manifest tests.

Verifies the canonical fixture manifest:
  - validates against `spiderweb_airspace_export` schema
  - every declared file exists, with matching sha256 and record_count
  - declares all four required streams exactly once
  - the validator CLI exits non-zero when the manifest is missing
  - the validator CLI reports a sha256 mismatch when a stream is tampered with
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "valid_airspace_export"
VALIDATOR = REPO_ROOT / "scripts" / "validate_export.py"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    with open(FIXTURE_DIR / "manifest.json") as f:
        return json.load(f)


def test_declared_files_exist_and_match_hash():
    manifest = _load_manifest()
    for entry in manifest["files"]:
        p = FIXTURE_DIR / entry["filename"]
        assert p.exists(), f"declared file missing: {p}"
        assert _sha256(p) == entry["sha256"], f"sha256 mismatch for {entry['filename']}"


def test_declared_record_counts_match_jsonl_lines():
    manifest = _load_manifest()
    for entry in manifest["files"]:
        p = FIXTURE_DIR / entry["filename"]
        with open(p, encoding="utf-8") as f:
            actual = sum(1 for line in f if line.strip())
        assert actual == entry["record_count"], (
            f"record_count mismatch for {entry['filename']}: "
            f"declared={entry['record_count']} actual={actual}"
        )


def test_manifest_declares_all_four_streams_exactly_once():
    manifest = _load_manifest()
    streams = [e["stream"] for e in manifest["files"]]
    assert sorted(streams) == ["events", "observations", "sources", "tracks"]
    assert len(streams) == len(set(streams))


def test_manifest_package_id_is_deterministic():
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.validate_export import compute_package_id
    manifest = _load_manifest()
    expected = compute_package_id(manifest)
    assert manifest["package_id"] == expected


def test_validator_cli_passes_on_fixture(tmp_path):
    # Run validator as a subprocess against an isolated copy so we don't trample
    # the canonical fixture's validation_report.json.
    copy = tmp_path / "pkg"
    shutil.copytree(FIXTURE_DIR, copy)
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--package", str(copy), "--mode", "test"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr={result.stderr}\nstdout={result.stdout}"
    report = json.loads((copy / "validation_report.json").read_text())
    assert report["status"] == "ok"


def test_validator_cli_fails_when_manifest_missing(tmp_path):
    copy = tmp_path / "pkg"
    shutil.copytree(FIXTURE_DIR, copy)
    (copy / "manifest.json").unlink()
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--package", str(copy), "--mode", "test"],
        capture_output=True, text=True,
    )
    assert result.returncode == 3
    assert "manifest not found" in result.stderr


def test_validator_cli_reports_sha_mismatch(tmp_path):
    copy = tmp_path / "pkg"
    shutil.copytree(FIXTURE_DIR, copy)
    # Tamper with a stream — append a byte to break the sha256.
    target = copy / "observations.jsonl"
    with open(target, "ab") as f:
        f.write(b"\n")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--package", str(copy), "--mode", "test"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    report = json.loads((copy / "validation_report.json").read_text())
    assert any("sha256 mismatch" in e for e in report["errors"])


def test_validator_cli_fails_production_mode_on_synthetic(tmp_path):
    copy = tmp_path / "pkg"
    shutil.copytree(FIXTURE_DIR, copy)
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--package", str(copy), "--mode", "production"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2, "production mode must reject synthetic rows"
    report = json.loads((copy / "validation_report.json").read_text())
    row_msgs = [m for fr in report["files"] for re_ in fr["row_errors"] for m in re_["errors"]]
    assert any("synthetic row not allowed in production mode" in m for m in row_msgs)
