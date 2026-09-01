from pathlib import Path


def test_second_sensor_receipt_is_present() -> None:
    path = Path("evidence/marine/GUAYAMA_SECOND_SENSOR_v0_5_RECEIPT.json")
    assert path.exists()


def test_second_sensor_scripts_are_present() -> None:
    for name in (
        "run_intersecting_multibeam_product_inventory.py",
        "run_ex1502l3_w00247_valid_overlap.py",
        "run_ex1502l3_vertical_adjudication.py",
        "run_ex1502l3_w00247_morphology_rank.py",
    ):
        assert Path("scripts", name).exists()
