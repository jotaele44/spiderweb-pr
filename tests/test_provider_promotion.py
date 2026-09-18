from __future__ import annotations

from spiderweb.provider_promotion import adjudicate_layer_denominator


def test_exact_layer_id_set_closure_is_promotion_eligible() -> None:
    provider = {"provisional_layers": [
        {"id": 20, "role": "hydrolocation"},
        {"id": 50, "role": "flowline"},
    ]}
    denominator = {
        "schema_version": "spiderweb.arcgis_layer_denominator.v1.0",
        "provider_id": "USGS_3DHP_NHD",
        "state": "PASS",
        "canonical_records_sha256": "a" * 64,
        "records": [
            {"layer_id": 20, "name_raw": "HydroLocation"},
            {"layer_id": 50, "name_raw": "Flowline"},
        ],
    }
    out = adjudicate_layer_denominator(
        provider_id="USGS_3DHP_NHD",
        provider=provider,
        denominator=denominator,
    )
    assert out["state"] == "PASS"
    assert out["promotion_eligible"] is True
    assert out["intersection"] == [20, 50]
    assert out["a_only_provisional"] == []
    assert out["b_only_frozen"] == []
    assert out["symmetric_difference"] == []


def test_count_equality_with_different_ids_is_not_identity() -> None:
    provider = {"provisional_layers": [{"id": 20}, {"id": 50}]}
    denominator = {
        "schema_version": "spiderweb.arcgis_layer_denominator.v1.0",
        "provider_id": "USGS_3DHP_NHD",
        "state": "PASS",
        "canonical_records_sha256": "b" * 64,
        "records": [{"layer_id": 20, "name_raw": "A"}, {"layer_id": 60, "name_raw": "B"}],
    }
    out = adjudicate_layer_denominator(
        provider_id="USGS_3DHP_NHD",
        provider=provider,
        denominator=denominator,
    )
    assert out["state"] == "REVIEW"
    assert out["promotion_eligible"] is False
    assert out["a_only_provisional"] == [50]
    assert out["b_only_frozen"] == [60]
    assert out["union"] == [20, 50, 60]
    assert out["symmetric_difference"] == [50, 60]
