from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
MODULE_PATH=ROOT/"scripts"/"acquire_jp_flood_documents.py"
spec=importlib.util.spec_from_file_location("jp_flood_docs",MODULE_PATH)
mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)

def _series_html():
    links=[]
    for m in mod.CANONICAL_MUNICIPALITIES:
        if m=="Florida": continue
        links.append(f'<a href="/uploads/Mapas Inundacion/{m.replace(" ","_")}_sectores_inundables.pdf">{m}</a>')
    return "\n".join(links)

def test_source_state_contract_closes_78():
    rows=mod.apply_known_exceptions(mod.discover_series(_series_html()))
    mod.validate(rows)
    assert len(rows)==78
    assert sum(r["source_state"]=="AVAILABLE" for r in rows)==76
    assert sum(r["source_state"]=="LISTED_BUT_MISSING" for r in rows)==1
    assert sum(r["source_state"]=="NOT_LISTED" for r in rows)==1

def test_quebradillas_is_listed_but_missing_with_fallback():
    rows=mod.apply_known_exceptions(mod.discover_series(_series_html()))
    q=next(r for r in rows if r["municipality"]=="Quebradillas")
    assert q["source_state"]=="LISTED_BUT_MISSING"
    assert q["fallback_document_class"]=="hazard_mitigation_plan"
    assert q["fallback_relationship"]=="authoritative_fallback_not_equivalent"

def test_florida_is_not_listed_with_fallback():
    rows=mod.apply_known_exceptions(mod.discover_series(_series_html()))
    f=next(r for r in rows if r["municipality"]=="Florida")
    assert f["source_state"]=="NOT_LISTED"
    assert f["equivalent_series_member"] is False
    assert f["fallback_document_class"]=="hazard_mitigation_plan"

def test_missing_municipality_fails_closed():
    rows=mod.apply_known_exceptions(mod.discover_series(_series_html()))
    with pytest.raises(AssertionError):
        mod.validate([r for r in rows if r["municipality"]!="Yauco"])
