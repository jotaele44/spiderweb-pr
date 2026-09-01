from pathlib import Path

from source_adapters.ncei_coastal_dem.registry import load_registry

FIXTURE = Path("tests/fixtures/ncei_coastal_dem/priority_datasets_fixture.csv")


def test_registry_loads_required_metadata() -> None:
    records = load_registry(FIXTURE)

    assert len(records) == 2
    assert records[0].dataset_id == "san_juan_19_prvd02_2015"
    assert records[0].raw_commit_allowed is False
    assert {record.priority for record in records} == {"P0", "P1"}


def test_registry_rejects_raw_commit_allowed_true(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "dataset_id,source_family,name,area,year,horizontal_datum,"
        "vertical_datum,resolution_arcsec,status,source_url,access_method,"
        "raw_commit_allowed,priority,notes\n"
        "x,NCEI_REGIONAL_DEM,X,X,2020,WGS84,MHW,1/3,live_thredds,"
        "https://example.com/x.nc,THREDDS,true,P0,bad\n",
        encoding="utf-8",
    )

    try:
        load_registry(bad)
    except ValueError as exc:
        assert "raw_commit_allowed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
