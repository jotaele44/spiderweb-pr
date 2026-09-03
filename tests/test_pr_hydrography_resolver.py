from __future__ import annotations

from scripts.source_adapters.pr_hydrography.resolver import resolve_document


def test_file_contract_preserves_ties_and_explicit_evidence():
    document = {
        "discovery_candidates": [
            {
                "source_a_id": "PR00011",
                "source_b_id": "26378301",
                "evidence_class": "DISTANCE_ONLY_WITHIN_500M",
                "evidence_rank": 10,
                "distance_m": 314.52,
                "explicit_hard_binding": False,
                "source_taxonomy": "FTYPE436",
            },
            {
                "source_a_id": "PR00029",
                "source_b_id": "A",
                "evidence_class": "DISTANCE_ONLY_WITHIN_100M",
                "evidence_rank": 8,
                "distance_m": 19.04,
                "explicit_hard_binding": False,
            },
            {
                "source_a_id": "PR00029",
                "source_b_id": "B",
                "evidence_class": "DISTANCE_ONLY_WITHIN_100M",
                "evidence_rank": 8,
                "distance_m": 19.78,
                "explicit_hard_binding": False,
            },
        ],
        "explicit_evidence_candidates": [
            {
                "source_a_id": "PR00011",
                "source_b_id": "120013183",
                "evidence_class": "HARD_V4_POLYGON_BINDING",
                "evidence_rank": 0,
                "distance_m": 7933.52,
                "explicit_hard_binding": True,
                "source_taxonomy": "FTYPE390",
            }
        ],
    }
    result = resolve_document(document)
    by_id = {row["source_a_id"]: row for row in result["results"]}
    assert by_id["PR00011"]["winner"]["source_b_id"] == "120013183"
    assert by_id["PR00029"]["state"] == "TOP_EVIDENCE_TIE_REVIEW"
    assert by_id["PR00029"]["winner"] is None
    assert result["universe_contract"]["source_taxonomy_is_identity"] is False
