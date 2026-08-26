from __future__ import annotations

from spiderweb.subsurface.public_exhaustion import current_public_exhaustion_certificate
from spiderweb.subsurface.residuals import (
    ResidualState,
    V05_RESIDUAL_ASSESSMENTS,
    V06_RESIDUAL_ASSESSMENTS,
)
from spiderweb.subsurface.sources_exhaustion_v05 import SOURCE_DENOMINATOR_V05
from spiderweb.subsurface.sources_exhaustion_v06 import BOUND_V06, SOURCE_DENOMINATOR_V06


def test_v06_adds_four_historical_workings_manifests_without_mutating_v05() -> None:
    assert len(BOUND_V06) == 4
    assert len(SOURCE_DENOMINATOR_V06) == len(SOURCE_DENOMINATOR_V05) + 4
    assert len({row.source_id for row in SOURCE_DENOMINATOR_V06}) == len(SOURCE_DENOMINATOR_V06)


def test_historic_workings_residual_reopens_only_in_current_v06_lineage() -> None:
    v05 = {row.source_id: row for row in V05_RESIDUAL_ASSESSMENTS}
    v06 = {row.source_id: row for row in V06_RESIDUAL_ASSESSMENTS}
    source_id = "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL"
    assert v05[source_id].state == ResidualState.FINAL_PUBLIC_GAP
    assert v06[source_id].state == ResidualState.OPEN
    assert v06[source_id].negative_evidence_permitted is False


def test_current_public_exhaustion_uses_v06_and_keeps_request_gate_closed() -> None:
    cert = current_public_exhaustion_certificate()
    assert cert.scope.endswith("V06")
    assert cert.records_request_eligible is False
    assert "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL" in cert.unresolved_sources


def test_v06_site78_manifest_is_supporting_not_direct_geometry() -> None:
    by_id = {row.source_id: row for row in BOUND_V06}
    site78 = by_id["OECH_CARRETERA_CENTRAL_CANTERA_NARANJO_1996"]
    assert site78.evidence_role == "SUPPORTING"
    assert "exact tunnel geometry" in site78.notes
