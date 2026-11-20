"""The declared search for an independent second seabed survey (V12)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from spiderweb.access_points import replication as rep
from spiderweb.access_points.survey_run import RUNS_PATH, SURVEY_DIR

REPO = Path(__file__).resolve().parents[1]
SEARCH_ID = "2026-11-20-offshore-replication"


def square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def test_points_inside_parts_and_holes_are_judged_by_the_even_odd_rule():
    outer = square(0, 0, 10, 10)
    hole = square(4, 4, 6, 6)
    other_part = square(20, 20, 30, 30)
    rings = [outer, hole, other_part]
    assert rep.polygon_contains(rings, 1, 1)
    assert not rep.polygon_contains(rings, 5, 5)  # in the hole
    assert rep.polygon_contains(rings, 25, 25)  # in the second part
    assert not rep.polygon_contains(rings, 15, 15)
    assert not rep.polygon_contains([], 1, 1)


def test_a_footprint_answer_is_read_cruise_by_cruise():
    payload = {
        "features": [
            {
                "attributes": {
                    "SURVEY_ID": "A1",
                    "PLATFORM": "NOAA Ship X",
                    "SURVEY_YEAR": 2010,
                },
                "geometry": {"rings": [square(0, 0, 10, 10)]},
            },
            {
                "attributes": {"SURVEY_ID": "A1"},
                "geometry": {"rings": [square(20, 0, 30, 10)]},
            },
            {
                "attributes": {"SURVEY_ID": "B2"},
                "geometry": {"rings": [square(50, 50, 60, 60)]},
            },
        ]
    }
    points = {"p": (5, 5), "q": (25, 5), "r": (90, 90)}
    cover = rep.footprint_cover(payload, points)
    assert cover["A1"]["contains"] == ["p", "q"]
    assert cover["A1"]["footprint_features"] == 2
    assert cover["B2"]["contains"] == []
    with pytest.raises(rep.ReplicationSearchError, match="not a feature list"):
        rep.footprint_cover({"error": {"code": 400}}, points)
    with pytest.raises(rep.ReplicationSearchError, match="names no survey"):
        rep.footprint_cover({"features": [{"attributes": {}}]}, points)


REFERENCE = {
    "vessel": "NOAA Ship NANCY FOSTER",
    "start_date": "2013-03-05",
    "instruments": "Kongsberg Maritime EM 1002 MBES Reson 7125 SV MBES",
}


@pytest.mark.parametrize(
    ("cruise", "relation"),
    [
        (
            {
                "platform": "NOAA Ship NANCY FOSTER (R352)",
                "survey_year": 2013,
                "instrument": "Kongsberg EM1002; Reson SeaBat 7125",
            },
            "PROBABLY_THE_SAME_SOUNDINGS",
        ),
        (
            {
                "platform": "NOAA Ship NANCY FOSTER (R352)",
                "survey_year": 2014,
                "instrument": "Kongsberg EM1002; Reson SeaBat 7125",
            },
            "INDEPENDENT_ACQUISITION",
        ),
        (
            {
                "platform": "NOAA Ship NANCY FOSTER (R352)",
                "survey_year": 2013,
                "instrument": "Kongsberg EM710",
            },
            "INDEPENDENT_ACQUISITION",
        ),
        (
            {
                "platform": "NOAA Ship RONALD H. BROWN (R104)",
                "survey_year": 2013,
                "instrument": "Reson 7125",
            },
            "INDEPENDENT_ACQUISITION",
        ),
    ],
)
def test_same_ship_year_and_instrument_is_probably_the_same_soundings(cruise, relation):
    result = rep.independence(cruise, REFERENCE)
    assert result["relation"] == relation
    assert result["basis"].startswith("INFERENCE")


def test_a_landing_page_is_read_for_vessel_dates_and_instruments():
    page = (
        b"<html><b>Start Date:</b> 2016-04-07 <b>End Date:</b> 2016-04-18 "
        b"<table><tr><th>Vessel(s)</th><th>Chief(s) of Party</th></tr>"
        b"<tr><td>NOAA Ship NANCY FOSTER</td><td>Timothy Battista</td></tr></table>"
        b"<table><tr><th>Manufacturer</th><th>Model</th><th>Instrument Type</th></tr>"
        b"<tr><td>Kongsberg Maritime</td><td>EM 710</td><td>MBES</td></tr></table>"
        b" Source Data at NCEI</html>"
    )
    facts = rep.landing_page_facts(page)
    assert facts["start_date"] == "2016-04-07" and facts["end_date"] == "2016-04-18"
    assert facts["vessel"] == "NOAA Ship NANCY FOSTER"
    assert "710" in facts["instruments"]


def test_file_categories_come_from_the_discovery_catalogue():
    catalogue = {
        "sources": [
            {
                "family": "MULTIBEAM_SURVEY_CATALOG",
                "native_identifier": "NCEI:multibeam:X1",
                "query_scoped_attributes": {
                    "fileStatsByCat": {
                        "t": [
                            {"name": "MB RAW", "count": 2, "size": 10},
                            {"name": "MB PROCESSED", "count": 1, "size": 5},
                        ]
                    }
                },
            },
            {
                "family": "MULTIBEAM_SURVEY_CATALOG",
                "native_identifier": "NCEI:multibeam:X2",
                "query_scoped_attributes": {"fileStatsByCat": {"other": []}},
            },
            {"family": "NOS_BAG_INVENTORY", "native_identifier": "NOS:BAG:Y"},
        ]
    }
    cats = rep.file_categories(catalogue, "t")
    assert list(cats) == ["X1"]
    assert [c["category"] for c in cats["X1"]] == ["MB PROCESSED", "MB RAW"]


def _config(tmp_path, mutate):
    data = yaml.safe_load((REPO / RUNS_PATH).read_text(encoding="utf-8"))
    mutate(data[rep.SEARCHES_KEY][0])
    path = tmp_path / "runs.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda s: s.update(lon=-65.9, lat=17.8), "may not state positions"),
        (lambda s: s.update(registry="access_point.inland"), "off-shore"),
        (lambda s: s.pop("earlier_run"), "earlier_run is required"),
        (lambda s: s["candidate_product"].update(sha256="xyz"), "64 hex"),
    ],
)
def test_a_search_states_no_position_and_names_its_evidence(tmp_path, mutate, message):
    with pytest.raises(rep.ReplicationSearchError, match=message):
        rep.load_search(_config(tmp_path, mutate), SEARCH_ID)


def _committed():
    path = REPO / SURVEY_DIR / SEARCH_ID / rep.REPORT_FILE
    if not path.is_file():
        pytest.skip("no replication search is committed")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_committed_search_is_reproduced_from_committed_evidence():
    _committed()
    search = rep.load_search(REPO / RUNS_PATH, SEARCH_ID)
    assert rep.check_report(search, repo_root=REPO) == []


def test_the_committed_search_overstates_nothing():
    report = _committed()
    assert report["registry_changes"] == 0
    assert report["outcome"] == "BLOCKED_INDEPENDENT_CRUISES_HOLD_RAW_SOUNDINGS_ONLY"
    assert report["independent_cruises_with_gridded_product_covering"] == []
    candidate = report["candidate_product"]
    assert candidate["covers"] == [] and candidate["outcome"].startswith("COVERS_NONE")
    assert (
        candidate["coverage"]["horizontal_crs_basis"]
        == "MATCHED_BY_PARAMETERS_NO_CODE_IN_FILE"
    )
    assert report["prior_gridded_product"]["reaches_the_depressions"] is False
    same = [
        r["survey_id"]
        for r in report["cruises"]
        if r["independence"]["relation"] == "PROBABLY_THE_SAME_SOUNDINGS"
    ]
    assert same == ["NF-13-02"]
    for row in report["cruises"]:
        if row["survey_id"] in report["independent_cruises_with_raw_soundings_only"]:
            assert row["contains"] and row["gridded_product_at_ncei"] is False
    assert any("not coverage" in limit for limit in report["limits"])


def test_changed_search_evidence_is_detected(tmp_path):
    _committed()
    for rel in (
        RUNS_PATH,
        rep.DISCOVERY_CATALOGUE,
        "evidence/marine/GUAYAMA_SECOND_SENSOR_v0_5_RECEIPT.json",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    for run in (SEARCH_ID, "2026-11-19-offshore-8m-small", "2026-11-18-offshore"):
        shutil.copytree(REPO / SURVEY_DIR / run, tmp_path / SURVEY_DIR / run)
    search = rep.load_search(tmp_path / RUNS_PATH, SEARCH_ID)
    assert rep.check_report(search, repo_root=tmp_path) == []

    def problems():
        return " ".join(rep.check_report(search, repo_root=tmp_path))

    footprints = (
        tmp_path
        / SURVEY_DIR
        / SEARCH_ID
        / "catalogue"
        / "ncei_multibeam_footprints.bin"
    )
    kept = footprints.read_bytes()
    footprints.write_bytes(kept + b" ")
    assert "does not match its manifest" in problems()
    footprints.write_bytes(kept)

    facts = tmp_path / SURVEY_DIR / SEARCH_ID / rep.FACTS_FILE
    kept_facts = facts.read_text()
    doc = json.loads(kept_facts)
    doc["coverage"]["points_within_one_base_cell"] = ["anything"]
    facts.write_text(json.dumps(doc))
    assert "does not match its content hash" in problems()
    facts.write_text(kept_facts)

    receipt = tmp_path / "evidence/marine/GUAYAMA_SECOND_SENSOR_v0_5_RECEIPT.json"
    doc = json.loads(receipt.read_text())
    doc["second_sensor"]["candidate_value_max"] = -50.0
    receipt.write_text(json.dumps(doc))
    assert "not reproduced" in problems()
