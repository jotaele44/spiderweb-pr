"""Theme 5 — reproducibility hardening for export adapters (T5-40).

Determinism invariant: running an exporter twice against the same DB state
produces byte-identical artifacts. We export TWICE inside each test and compare
hash(run1) vs hash(run2) — both fresh against the current DB. Comparing two
fresh runs (rather than on-disk vs fresh) keeps this a determinism test, not a
stale-artifact tripwire.

The timestamped manifest (spiderweb_ingest_manifest.json, which embeds
generated_at + reproducibility timestamp_utc) is intentionally excluded — only
the content-deterministic artifacts are compared.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from integration.aasb_airspace_bridge import AASBAirspaceBridge
from integration.ilap_airspace_bridge import ILAPAirspaceBridge


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── ILAP GeoJSON determinism ─────────────────────────────────────────────────

def test_ilap_export_is_reproducible(populated_db, tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    ILAPAirspaceBridge(populated_db, str(out1)).export_all()
    ILAPAirspaceBridge(populated_db, str(out2)).export_all()

    names = [
        "airspace_poi_candidates.geojson",
        "airspace_ilap_candidates.geojson",
        "airspace_corridor_candidates.geojson",
    ]
    diffs = [n for n in names if _hash(out1 / n) != _hash(out2 / n)]
    assert not diffs, f"ILAP exports not reproducible: {diffs}"


def test_ilap_second_export_same_dir_is_stable(populated_db, tmp_path):
    """Re-exporting into the same directory must overwrite to identical bytes."""
    out = tmp_path / "out"
    ILAPAirspaceBridge(populated_db, str(out)).export_all()
    h1 = _hash(out / "airspace_poi_candidates.geojson")
    ILAPAirspaceBridge(populated_db, str(out)).export_all()
    h2 = _hash(out / "airspace_poi_candidates.geojson")
    assert h1 == h2


# ── AASB edge CSV determinism ────────────────────────────────────────────────

def test_aasb_edge_csv_is_reproducible(populated_db, tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    AASBAirspaceBridge(populated_db, str(out1)).export_all()
    AASBAirspaceBridge(populated_db, str(out2)).export_all()

    csv_name = "aasb_airspace_edges.csv"
    assert _hash(out1 / csv_name) == _hash(out2 / csv_name), (
        "AASB edge CSV not reproducible across two fresh exports"
    )
