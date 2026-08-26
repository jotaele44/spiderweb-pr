from pathlib import Path

from source_adapters.ncei_coastal_dem.fetch_plan import build_fetch_plan
from source_adapters.ncei_coastal_dem.registry import load_registry

FIXTURE = Path("tests/fixtures/ncei_coastal_dem/priority_datasets_fixture.csv")


def test_discover_plan_is_metadata_only_by_default() -> None:
    plan = build_fetch_plan(load_registry(FIXTURE), metadata_only=True)

    assert plan["metadata_only"] is True
    assert plan["selected_count"] == 2
    assert all(task["metadata_only"] is True for task in plan["tasks"])
    assert all(task["local_cache_path"] is None for task in plan["tasks"])
    assert all(task["raw_commit_allowed"] is False for task in plan["tasks"])


def test_fetch_plan_for_single_dataset_sets_cache_path() -> None:
    plan = build_fetch_plan(
        load_registry(FIXTURE),
        dataset_id="san_juan_19_prvd02_2015",
        metadata_only=False,
        cache_dir=Path("data/ncei_coastal_dem/cache"),
    )

    assert plan["selected_count"] == 1
    assert plan["tasks"][0]["local_cache_path"].endswith(
        "san_juan_19_prvd02_2015.nc"
    )
    assert plan["tasks"][0]["review_status"] == "planned_raw_cache_fetch"
