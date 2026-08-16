from pipeline.pr_marine_datasets import (
    DatasetRole,
    PUERTO_RICO_MARINE_DATASETS,
    dataset_by_id,
)


def test_registry_ids_are_unique() -> None:
    ids = [item.dataset_id for item in PUERTO_RICO_MARINE_DATASETS]
    assert len(ids) == len(set(ids))


def test_sensor_and_derived_roles_are_not_conflated() -> None:
    assert dataset_by_id("9390").role is DatasetRole.SENSOR_POINT_CLOUD
    assert dataset_by_id("8571").role is DatasetRole.DERIVED_DEM
    assert dataset_by_id("9524").role is DatasetRole.FUSED_COASTAL_DEM


def test_known_bulk_url_lists_are_https() -> None:
    for item in PUERTO_RICO_MARINE_DATASETS:
        if item.url_list_url is not None:
            assert item.url_list_url.startswith("https://")


def test_unknown_dataset_id_fails_closed() -> None:
    try:
        dataset_by_id("not-present")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown registry ID must raise KeyError")
