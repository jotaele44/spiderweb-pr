"""Bounded TIGER2026 Puerto Rico inventory: directory evidence, not ingested geometry."""
import csv
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tiger" / "2026"
BASE = "https://www2.census.gov/geo/tiger/TIGER2026/"
MUNICIPAL_FAMILIES = {
    "ADDR", "ADDRFEAT", "ADDRFN", "AREAWATER", "EDGES",
    "FACES", "FACESAH", "FEATNAMES", "LINEARWATER", "ROADS",
}

def read(name):
    with (DATA / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def test_pr_exact_vintage_directory_universe():
    rows = read("pr_source_inventory.csv")
    assert len(rows) == 796
    assert len({r["url"] for r in rows}) == 796
    assert all(r["verification"] == "INDEX_LISTED" for r in rows)
    states = [r for r in rows if r["scope"] == "PR_STATEWIDE"]
    towns = [r for r in rows if r["scope"] == "PR_MUNICIPALITY"]
    assert len(states) == 16
    assert len(towns) == 780
    assert len({r["geo_fips"] for r in towns}) == 78
    assert {r["category"] for r in towns} == MUNICIPAL_FAMILIES
    assert all(n == 78 for n in Counter(r["category"] for r in towns).values())
    for row in rows:
        assert row["url"].startswith(BASE + row["category"] + "/")
        assert urlparse(row["url"]).scheme == "https"
        assert row["filename"].startswith("tl_2026_" + row["geo_fips"] + "_")
        assert row["url"].endswith("/" + row["filename"])

def test_national_candidates_are_not_mislabeled_pr_certified():
    rows = read("us_candidate_inventory.csv")
    assert len(rows) == 17
    assert len({r["url"] for r in rows}) == len(rows)
    assert all(r["scope"] == "US_CANDIDATE_CONTENT_UNVERIFIED" for r in rows)
    assert all(r["verification"] == "INDEX_LISTED_PR_MEMBERSHIP_UNVERIFIED" for r in rows)
    assert all(r["filename"].startswith("tl_2026_us_") for r in rows)
    assert all(r["url"].startswith(BASE + r["category"] + "/") for r in rows)
