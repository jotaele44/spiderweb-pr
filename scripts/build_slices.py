#!/usr/bin/env python3
"""Slice the canonical natural-features master into per-consumer datasets.

spiderweb-pr owns the full gazetteer; each downstream producer consumes only its
domain slice under the federation contract (see docs/NATURAL_FEATURES_CONTRACT.md):

  aguayluz-pr          -> hydro group           (environmental + water infra)
  skywatcher-pr/ovnis  -> terrain + coastal     (above/below surface, approaches)
  centinelas-pr        -> all groups, name-only  (resolver: no geometry)
  moneysweep-pr        -> none (municipality context via its existing crosswalk)

Writes slices under ``data/natural_features/slices/`` for vendoring into the
consumer repos. Each slice carries the master's provenance header so a consumer
can pin the source version + sha.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "registry" / "natural_features"
SLICES = DATA / "slices"

RESOLVER_FIELDS = ("canonical_id", "canonical_name", "normalized_name",
                   "municipality", "feature_type", "group")


def _master() -> dict:
    return json.loads((DATA / "pr_natural_features.json").read_text(encoding="utf-8"))


def _header(master: dict) -> dict:
    return {k: v for k, v in master.items() if k.startswith("_") and k != "_count"}


def _write_full(path: Path, header: dict, recs: list[dict]) -> None:
    path.write_text(json.dumps({**header, "_count": len(recs), "features": recs},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def _write_geojson(path: Path, recs: list[dict]) -> None:
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": {k: r[k] for k in ("canonical_id", "gnis_id", "canonical_name",
                        "normalized_name", "feature_type", "group", "feature_class",
                        "municipality")}}
        for r in recs]}
    path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    master = _master()
    header = _header(master)
    recs = master["features"]
    SLICES.mkdir(parents=True, exist_ok=True)

    hydro = [r for r in recs if r["group"] == "hydro"]
    terr_coast = [r for r in recs if r["group"] in ("terrain", "coastal")]

    _write_full(SLICES / "aguayluz_pr_natural_features.json", header, hydro)
    _write_geojson(SLICES / "aguayluz_pr_natural_features.geojson", hydro)
    _write_full(SLICES / "skywatcher_ovnis_pr_natural_features.json", header, terr_coast)
    _write_geojson(SLICES / "skywatcher_ovnis_pr_natural_features.geojson", terr_coast)

    resolver = [{k: r[k] for k in RESOLVER_FIELDS} for r in recs]
    (SLICES / "centinelas_pr_natural_features_resolver.json").write_text(
        json.dumps({**header, "_count": len(resolver), "_projection": "resolver_name_only",
                    "features": resolver}, ensure_ascii=False, indent=2), encoding="utf-8")

    assert len(hydro) + len(terr_coast) == len(recs), "slice union != master"
    print(f"slices: aguayluz(hydro)={len(hydro)} "
          f"skywatcher/ovnis(terrain+coastal)={len(terr_coast)} "
          f"centinelas(resolver)={len(resolver)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
