"""Config-registry tests: providers, confidence model, AOIs, layer catalog."""

from pipeline.config_loader import load_yaml_config
from spiderweb.remote_monitoring import active_aois, load_aois


def test_providers_registry_planet_nicfi_disabled():
    cfg = load_yaml_config(
        "configs/remote_monitoring/providers.yaml", required_keys=["providers"]
    )
    planet = cfg["providers"]["planet_nicfi"]
    assert planet["enabled"] is False
    assert planet["status"] == "entitlement_required"
    assert planet["redistribution"] == "unresolved"


def test_sentinel1_revisit_is_observed_not_assumed():
    cfg = load_yaml_config("configs/remote_monitoring/providers.yaml")
    assert (
        cfg["providers"]["sentinel_1_grd"]["revisit_policy"] == "observed_from_catalog"
    )


def test_3dep_requires_two_epochs_for_volume():
    cfg = load_yaml_config("configs/remote_monitoring/providers.yaml")
    assert (
        cfg["providers"]["usgs_3dep_lidar"]["volume_change_requires_two_epochs"] is True
    )


def test_confidence_model_components_sum_100():
    cfg = load_yaml_config(
        "configs/remote_monitoring/confidence_model.yaml",
        required_keys=["components", "bands"],
    )
    assert sum(cfg["components"].values()) == 100


def test_layer_config_carries_guardrails():
    cfg = load_yaml_config(
        "configs/layers/remote_monitoring.yaml",
        required_keys=["layer_id", "guardrails"],
    )
    g = cfg["guardrails"]
    assert g["candidate_before_confirmed"] is True
    assert g["no_signal_never_implies_non_performance"] is True
    assert g["sar_revisit_cadence"] == "observed_from_catalog"


def test_layer_config_registers_output_layers():
    # The subsystem registers itself through its own per-layer config (the same
    # granularity Head Start uses). Master layer_catalog + pin-registry wiring is
    # deferred until the subsystem is pipeline-wired.
    cfg = load_yaml_config(
        "configs/layers/remote_monitoring.yaml",
        required_keys=["layer_id", "output_layers"],
    )
    assert cfg["layer_id"] == "rm_monitoring_pr"
    assert "rm_observations" in cfg["output_layers"]
    assert "rm_contract_crosswalk" in cfg["output_layers"]


def test_aois_load_and_are_in_pr_bounds():
    aois = load_aois()
    assert {a.aoi_uid for a in aois} == {
        "rm_aoi_carraizo_reservoir",
        "rm_aoi_cordillera_landslide_corridor",
    }
    assert all(a.in_pr_bounds() for a in aois)


def test_only_carraizo_is_active_pilot():
    act = active_aois()
    assert [a.aoi_uid for a in act] == ["rm_aoi_carraizo_reservoir"]
