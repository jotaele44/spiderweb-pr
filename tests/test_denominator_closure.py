from __future__ import annotations

import hashlib
import json
from pathlib import Path

from spiderweb.denominator_closure import close_discovery_denominators


def _receipt(provider: str, role: str, raw_path: Path) -> dict:
    raw = raw_path.read_bytes()
    return {
        "provider_id": provider,
        "request_role": role,
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "raw_path": str(raw_path),
    }


def test_scoped_3dhp_closure_can_promote_exact_stable_id_set(tmp_path: Path) -> None:
    raw_path = tmp_path / "3dhp.raw"
    raw_path.write_text(json.dumps({
        "layers": [
            {"id": 20, "name": "Hydrolocation A"},
            {"id": 50, "name": "Flowline"},
        ]
    }), encoding="utf-8")
    fetch = {
        "execution_scope": "DISCOVERY_OR_RESOLVER_STAGE",
        "state": "DISCOVERY_PASS",
        "requests": [_receipt("USGS_3DHP_NHD", "feature_service_metadata", raw_path)],
    }
    registry = {
        "providers": {
            "USGS_3DHP_NHD": {
                "provisional_layers": [
                    {"id": 20, "role": "hydrolocation"},
                    {"id": 50, "role": "flowline"},
                ]
            }
        }
    }
    out = close_discovery_denominators(
        fetch=fetch,
        registry=registry,
        query={"query_id": "x", "geometry": {"type": "point", "lat": 18.3, "lon": -66.0}},
        output_dir=tmp_path / "out",
    )
    assert out["state"] == "PASS"
    assert out["provider_record_count"] == 1
    record = out["records"][0]
    assert record["provider_id"] == "USGS_3DHP_NHD"
    assert record["promotion_eligible"] is True
    adjudication = json.loads(Path(record["adjudication_path"]).read_text(encoding="utf-8"))
    assert adjudication["intersection"] == [20, 50]
    assert adjudication["a_only_provisional"] == []
    assert adjudication["b_only_frozen"] == []
    assert adjudication["symmetric_difference"] == []


def test_scoped_closure_does_not_treat_unqueried_provider_as_absent(tmp_path: Path) -> None:
    fetch = {
        "execution_scope": "DISCOVERY_OR_RESOLVER_STAGE",
        "state": "DISCOVERY_PASS",
        "requests": [],
    }
    registry = {
        "providers": {
            "USGS_3DHP_NHD": {"provisional_layers": [{"id": 20, "role": "x"}]},
            "FEMA_NFHL": {},
            "FEMA_PR_ABFE_1PCT": {},
            "USACE_GENERAL_GIS": {"service_root": "https://example.invalid/rest/services"},
        }
    }
    out = close_discovery_denominators(
        fetch=fetch,
        registry=registry,
        query={"query_id": "x", "geometry": {"type": "point", "lat": 18.3, "lon": -66.0}},
        output_dir=tmp_path / "out",
    )
    assert out["state"] == "PASS"
    assert out["provider_record_count"] == 0
    assert out["records"] == []


def test_fema_nfhl_arcgis_layer_denominator_remains_dependent_stage(tmp_path: Path) -> None:
    raw_path = tmp_path / "nfhl.raw"
    raw_path.write_text(json.dumps({
        "layers": [
            {"id": 28, "name": "Flood Hazard Zones", "parentLayerId": -1, "subLayerIds": None},
            {"id": 16, "name": "Base Flood Elevations", "parentLayerId": -1, "subLayerIds": None},
        ]
    }), encoding="utf-8")
    fetch = {
        "execution_scope": "DISCOVERY_OR_RESOLVER_STAGE",
        "state": "DISCOVERY_PASS",
        "requests": [_receipt("FEMA_NFHL", "nfhl_map_service_denominator", raw_path)],
    }
    registry = {"providers": {"FEMA_NFHL": {}}}
    out = close_discovery_denominators(
        fetch=fetch,
        registry=registry,
        query={"query_id": "x", "geometry": {"type": "point", "lat": 18.3, "lon": -66.0}},
        output_dir=tmp_path / "out",
    )
    record = out["records"][0]
    assert record["promotion_eligible"] is False
    assert record["state"] == "LAYER_DENOMINATOR_PASS_DEPENDENT_AOI_OPEN"
    denominator = json.loads(Path(record["denominator_path"]).read_text(encoding="utf-8"))
    assert denominator["layer_count"] == 2
    assert {row["layer_id"] for row in denominator["records"]} == {16, 28}


def test_usace_root_with_folder_remains_open_and_emits_next_stage(tmp_path: Path) -> None:
    raw_path = tmp_path / "usace.raw"
    raw_path.write_text(json.dumps({
        "services": [{"name": "Ports", "type": "FeatureServer"}],
        "folders": ["Navigation"],
    }), encoding="utf-8")
    fetch = {
        "execution_scope": "DISCOVERY_OR_RESOLVER_STAGE",
        "state": "DISCOVERY_PASS",
        "requests": [_receipt("USACE_GENERAL_GIS", "services_root_denominator", raw_path)],
    }
    registry = {
        "providers": {
            "USACE_GENERAL_GIS": {
                "service_root": "https://example.invalid/arcgis/rest/services",
            }
        }
    }
    out = close_discovery_denominators(
        fetch=fetch,
        registry=registry,
        query={"query_id": "x", "geometry": {"type": "bbox", "west": -67, "south": 17, "east": -65, "north": 19}},
        output_dir=tmp_path / "out",
    )
    record = out["records"][0]
    assert record["state"] == "OPEN_RECURSIVE_FOLDER_DENOMINATOR"
    assert record["folder_count"] == 1
    next_plan = json.loads(Path(record["next_stage_plan_path"]).read_text(encoding="utf-8"))
    assert next_plan["fetch_gate"] == "READY"
    assert any(r["request_role"] == "folder_services:Navigation" for r in next_plan["requests"])
