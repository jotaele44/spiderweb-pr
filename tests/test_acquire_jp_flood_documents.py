from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "acquire_jp_flood_documents.py"

spec = importlib.util.spec_from_file_location("jp_flood_docs", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _series_html() -> str:
    links = []
    for municipality in mod.CANONICAL_MUNICIPALITIES:
        if municipality == "Florida":
            continue
        filename = municipality.replace(" ", "_") + "_sectores_inundables.pdf"
        links.append(
            f'<a href="/uploads/Mapas Inundacion/{filename}">{municipality}</a>'
        )
    return "\n".join(links)


def _with_florida_alt(rows: list[dict]) -> list[dict]:
    return rows + [{
        "municipality": "Florida",
        "municipality_raw": "Florida",
        "document_class": "hazard_mitigation_plan",
        "source_series": "JP_FLORIDA_HAZARD_MITIGATION_PLAN",
        "equivalent_series_member": False,
        "source_url": mod.FLORIDA_URL,
        "source_url_raw_href": None,
        "authority": "Junta de Planificación de Puerto Rico",
        "relationship_to_series": "authoritative_alternate_not_equivalent",
        "series_absence_state": "outside_source_series_provisional",
    }]


def test_77_series_plus_florida_alt_closes_78_municipalities() -> None:
    rows = mod.discover_series(_series_html())
    assert len(rows) == 77
    assert all(r["municipality"] != "Florida" for r in rows)

    combined = _with_florida_alt(rows)
    mod.validate(combined)

    assert len(combined) == 78
    assert sum(r["document_class"] == "flood_risk_zone_map" for r in combined) == 77
    assert sum(r["document_class"] == "hazard_mitigation_plan" for r in combined) == 1


def test_florida_cannot_be_promoted_into_series() -> None:
    rows = _with_florida_alt(mod.discover_series(_series_html()))
    rows.append({
        "municipality": "Florida",
        "municipality_raw": "Florida",
        "document_class": "flood_risk_zone_map",
        "source_series": "JP_SECTORES_EN_ZONA_INUNDABLES",
        "equivalent_series_member": True,
        "source_url": "https://example.invalid/Florida_sectores_inundables.pdf",
        "source_url_raw_href": None,
        "authority": "fixture",
    })
    with pytest.raises(AssertionError):
        mod.validate(rows)


def test_missing_municipality_fails_closed() -> None:
    rows = _with_florida_alt(mod.discover_series(_series_html()))
    trimmed = [r for r in rows if r["municipality"] != "Yauco"]
    with pytest.raises(AssertionError):
        mod.validate(trimmed)
