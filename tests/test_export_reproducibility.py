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


def _canonical_geojson(path: Path) -> str:
    """Load a GeoJSON and strip the wall-clock `_meta.produced_at` from every
    feature so two fresh exports compare on substantive content only.

    `produced_at` is an intentional emission timestamp (T7-57) — like the AASB
    manifest's `generated_at`, it is legitimately non-deterministic and excluded
    from the byte-identical determinism guarantee.
    """
    import json

    data = json.loads(path.read_text())
    for feat in data.get("features", []):
        meta = feat.get("properties", {}).get("_meta")
        if isinstance(meta, dict):
            meta.pop("produced_at", None)
    return json.dumps(data, sort_keys=True)


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
    diffs = [
        n for n in names
        if _canonical_geojson(out1 / n) != _canonical_geojson(out2 / n)
    ]
    assert not diffs, f"ILAP exports not reproducible (content): {diffs}"


def test_ilap_second_export_same_dir_is_stable(populated_db, tmp_path):
    """Re-exporting into the same directory must overwrite to identical content
    (ignoring the wall-clock _meta.produced_at emission stamp)."""
    out = tmp_path / "out"
    ILAPAirspaceBridge(populated_db, str(out)).export_all()
    c1 = _canonical_geojson(out / "airspace_poi_candidates.geojson")
    ILAPAirspaceBridge(populated_db, str(out)).export_all()
    c2 = _canonical_geojson(out / "airspace_poi_candidates.geojson")
    assert c1 == c2


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
