from __future__ import annotations

import hashlib
import json

import pytest

from spiderweb.provider_denominators import (
    DenominatorError,
    freeze_arcgis_layer_denominator,
    freeze_arcgis_service_denominator,
    freeze_wms_layer_denominator,
)


def receipt(provider: str, role: str, raw: bytes) -> dict:
    return {
        "provider_id": provider,
        "request_role": role,
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_arcgis_layer_denominator_sorts_and_preserves_names() -> None:
    raw = json.dumps({"layers": [{"id": 50, "name": "Flowline"}, {"id": 20, "name": "Hydrolocation"}]}).encode()
    out = freeze_arcgis_layer_denominator(
        raw=raw,
        receipt=receipt("USGS_3DHP_NHD", "feature_service_metadata", raw),
        provider_id="USGS_3DHP_NHD",
        request_role="feature_service_metadata",
    )
    assert [r["layer_id"] for r in out["records"]] == [20, 50]
    assert out["layer_count"] == 2
    assert out["layer_ids_unique"] is True


def test_arcgis_layer_denominator_rejects_duplicate_id() -> None:
    raw = json.dumps({"layers": [{"id": 1, "name": "A"}, {"id": 1, "name": "B"}]}).encode()
    with pytest.raises(DenominatorError, match="duplicate ArcGIS layer id"):
        freeze_arcgis_layer_denominator(
            raw=raw,
            receipt=receipt("X", "Y", raw),
            provider_id="X",
            request_role="Y",
        )


def test_arcgis_service_denominator_closes_services_and_folders() -> None:
    raw = json.dumps({
        "services": [
            {"name": "B", "type": "FeatureServer"},
            {"name": "A", "type": "MapServer"},
        ],
        "folders": ["z", "a", "a"],
    }).encode()
    out = freeze_arcgis_service_denominator(
        raw=raw,
        receipt=receipt("USACE_GENERAL_GIS", "services_root_denominator", raw),
        provider_id="USACE_GENERAL_GIS",
        request_role="services_root_denominator",
    )
    assert out["service_count"] == 2
    assert out["folders"] == ["a", "z"]


def test_wms_denominator_uses_named_layers_only() -> None:
    raw = b"""<WMS_Capabilities><Capability><Layer><Title>root</Title><Layer><Name>FLD_HAZ_AR</Name><Title>Flood Hazard Areas</Title></Layer><Layer><Name>FIRM_PAN</Name><Title>FIRM Panels</Title></Layer></Layer></Capability></WMS_Capabilities>"""
    out = freeze_wms_layer_denominator(
        raw=raw,
        receipt=receipt("FEMA_NFHL", "nfhl_wms_capabilities", raw),
        provider_id="FEMA_NFHL",
        request_role="nfhl_wms_capabilities",
    )
    assert out["layer_count"] == 2
    assert {r["name_raw"] for r in out["records"]} == {"FLD_HAZ_AR", "FIRM_PAN"}


def test_raw_hash_mismatch_fails_closed() -> None:
    raw = b'{"layers":[]}'
    bad = receipt("X", "Y", raw)
    bad["sha256"] = "0" * 64
    with pytest.raises(DenominatorError, match="SHA256"):
        freeze_arcgis_layer_denominator(raw=raw, receipt=bad, provider_id="X", request_role="Y")
