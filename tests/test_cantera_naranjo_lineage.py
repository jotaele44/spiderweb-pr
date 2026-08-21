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


def test_known_points_do_not_auto_bind_to_sz0015() -> None:
    rows = adjudicate_manifestations(
        aoi=_santiago_aoi(),
        zones=(("SZ-0015", _sz0015()),),
    )
    by_id = {row["manifestation_id"]: row for row in rows}

    # All three point manifestations are outside the frozen Santiago AOI. This
    # prevents the newly recovered historical-working evidence from silently
    # increasing the SZ-0015 score.
    assert by_id["USGS_W701145_JUANA_DIAZ_MINE"]["aoi_spatial_state"] == "OUTSIDE"
    assert by_id["PROCAN_EMBEDDED_MAP_CENTER"]["aoi_spatial_state"] == "OUTSIDE"
    assert by_id["EPA_PRODUCTOS_AGREGADOS_CANTERA_NARANJO"]["aoi_spatial_state"] == "OUTSIDE"

    assert all(row["containing_zones"] == [] for row in rows)
    assert all(row["promotion_permitted"] is False for row in rows)
    assert all(row["connectivity_inference_permitted"] is False for row in rows)


def test_identity_remains_unresolved_despite_name_and_history_overlap() -> None:
    assert KNOWN_POINT_MANIFESTATIONS
    assert all(row.identity_to_site78 == IdentityState.UNRESOLVED for row in KNOWN_POINT_MANIFESTATIONS)
