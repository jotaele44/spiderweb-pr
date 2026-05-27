from pathlib import Path

from pipeline.normalize_locations import normalize_location
from pipeline.normalize_missions import normalize_blackout, normalize_mission
from pipeline.normalize_operators import normalize_aircraft_identity, normalize_operator
from pipeline.rlsm_ontology_gate import run_gate

CONFIG_DIR = Path("configs")


def test_airport_alias_resolution():
    for value in ["SJU", "TJSJ", "Luis Munoz Marin", "Isla Grande", "BQN"]:
        assert normalize_location(value, CONFIG_DIR)["normalized_id"] is not None


def test_na_identity_policy():
    record = normalize_aircraft_identity("N/A", "B407")
    assert record["identity_status"] == "masked_or_unresolved"
    assert record["tail_canonical"] is None
    assert record["merge_policy"] == "do_not_merge_without_cluster_evidence"


def test_operator_alias_resolution():
    record = normalize_operator("USCG", CONFIG_DIR)
    assert record["resolution_status"] == "resolved"
    assert record["operator_id"] == "op_uscg_cluster"


def test_mission_alias_resolution():
    assert normalize_mission("grid inspection", CONFIG_DIR)["mission_canonical"] == "UTILITY_INSPECTION"
    assert normalize_mission("coastal patrol", CONFIG_DIR)["mission_canonical"] == "MARITIME_PATROL"
    assert normalize_mission("private charter", CONFIG_DIR)["mission_canonical"] == "PRIVATE_CHARTER"


def test_gap_terms_preserve_uncertainty():
    record = normalize_blackout("track gap", CONFIG_DIR)
    assert record["blackout_class"] != "UNKNOWN"
    assert record["do_not_assume_intentional"] is True


def test_gate_passes():
    result = run_gate(CONFIG_DIR)
    assert result["status"] == "pass", result
    assert result["ocr_baseline_allowed"] is True
