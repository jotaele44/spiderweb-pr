from __future__ import annotations

from shapely.geometry import Polygon

from spiderweb.subsurface.cantera_naranjo import (
    KNOWN_POINT_MANIFESTATIONS,
    SITE78_CLAIMS,
    IdentityState,
    adjudicate_manifestations,
)


def _santiago_aoi() -> Polygon:
    return Polygon(
        [
            (-66.29022746754467, 18.16435705124312),
            (-66.56454144076723, 18.01550664285417),
            (-66.01850153750115, 18.01784305432528),
        ]
    )


def _sz0015() -> Polygon:
    return Polygon(
        [
            (-66.46000000000002, 18.06),
            (-66.48000000000002, 18.06),
            (-66.48000000000002, 18.06138118521217),
            (-66.46000000000002, 18.07223374271336),
        ]
    )


def test_site78_claim_denominator_is_explicit() -> None:
    assert len(SITE78_CLAIMS) == 11
    km_claim = next(row for row in SITE78_CLAIMS if row.claim_id == "CN78-C02")
    assert "kilometer 4" in km_claim.text
    assert "4.4" not in km_claim.text


def test_historical_mine_point_does_not_auto_bind_to_sz0015() -> None:
    rows = adjudicate_manifestations(
        aoi=_santiago_aoi(),
        zones=(("SZ-0015", _sz0015()),),
    )
    by_id = {row["manifestation_id"]: row for row in rows}

    # The independent USGS Juana Diaz Mine record point remains just outside the
    # frozen AOI/SZ-0015. Modern Procan and EPA facility/map points are outside
    # as well. None can add a historical-working score to SZ-0015.
    for source_id in (
        "USGS_W701145_JUANA_DIAZ_MINE",
        "PROCAN_EMBEDDED_MAP_CENTER",
        "EPA_PRODUCTOS_AGREGADOS_CANTERA_NARANJO",
    ):
        assert by_id[source_id]["aoi_spatial_state"] == "OUTSIDE"
        assert by_id[source_id]["containing_zones"] == []

    # A different PRPB manifestation named CANTERA NARANJO is already inside
    # SZ-0015 and was already counted as quarry evidence in v1/v1.1. Its spatial
    # presence does not establish identity with historical Site 78 or W701145.
    prpb = by_id["PRPB_CANTERA_NARANJO_OBJECTID_38"]
    assert prpb["aoi_spatial_state"] == "WITHIN"
    assert prpb["containing_zones"] == ["SZ-0015"]

    # The MRDS Cantero Naranjo point is distinct again and outside the triangle.
    mrds = by_id["USGS_MRDS_CANTERO_NARANJO_200733"]
    assert mrds["aoi_spatial_state"] == "OUTSIDE"
    assert mrds["containing_zones"] == []

    assert all(row["promotion_permitted"] is False for row in rows)
    assert all(row["connectivity_inference_permitted"] is False for row in rows)


def test_identity_remains_unresolved_despite_name_and_history_overlap() -> None:
    assert KNOWN_POINT_MANIFESTATIONS
    assert all(row.identity_to_site78 == IdentityState.UNRESOLVED for row in KNOWN_POINT_MANIFESTATIONS)
