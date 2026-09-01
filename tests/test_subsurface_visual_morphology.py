import json

from spiderweb.subsurface.zone_evidence_pack import build_top8_pack


def _zone():
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        "properties": {
            "zone_id": "SZ-X",
            "score": 4.5,
            "relevance": "MODERATE",
            "v11_score": 4.4,
            "v11_relevance": "MODERATE",
            "sensitivity_state": "THRESHOLD",
        },
    }


def test_visual_morphology_is_injected_but_cannot_change_score():
    v11 = {"type": "FeatureCollection", "features": [_zone()]}
    evidence = {"type": "FeatureCollection", "features": []}
    visual = {
        "assessments": [
            {
                "image_file": "x.jpeg",
                "zone_id": "SZ-X",
                "binding_state": "AUTHORITATIVE_LANDMARK",
                "morphology_class": "SURFACE_QUARRY",
                "visible_subsurface_indicator": "SURFACE_EXTRACTION_ONLY",
                "promotion_permitted": True,
            }
        ]
    }
    pack, overlay = build_top8_pack(v11, evidence, {"assets": []}, visual)
    dossier = pack["zones"][0]
    assert dossier["v11_score"] == 4.4
    assert dossier["visual_morphology"][0]["promotion_permitted"] is False
    assert dossier["visual_morphology_summary"]["score_effect"] == 0.0
    assert overlay["features"][0]["properties"]["visual_morphology_score_effect"] == 0.0


def test_ambiguous_unbound_image_is_not_forced_into_zone():
    v11 = {"type": "FeatureCollection", "features": [_zone()]}
    visual = {
        "assessments": [
            {
                "image_file": "ambiguous.jpeg",
                "zone_id": None,
                "binding_state": "UNRESOLVED",
                "morphology_class": "GRADING_DISTURBANCE",
                "visible_subsurface_indicator": "NONE_VISIBLE",
            }
        ]
    }
    pack, _ = build_top8_pack(v11, {"type": "FeatureCollection", "features": []}, {"assets": []}, visual)
    assert pack["zones"][0]["visual_morphology"] == []
    assert pack["zones"][0]["visual_morphology_summary"]["visible_subsurface_indicator"] == "UNRESOLVED"
