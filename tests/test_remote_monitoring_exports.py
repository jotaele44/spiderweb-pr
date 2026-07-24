"""Export tests: rm_* GeoJSON layers carry _meta and a reproducibility manifest."""

import json

from spiderweb.remote_monitoring import (
    RemoteObservation,
    active_aois,
    adjudicate,
    exports,
    schemas,
)
from spiderweb.remote_monitoring.crosswalk import PhysicalContractCrosswalk, reconcile


def _observation():
    return RemoteObservation(
        aoi_uid="rm_aoi_carraizo_reservoir",
        scene_uids=["S2_x"],
        detector_name="turbidity_proxy",
        detector_version="0.1",
        signals=[schemas.SIGNAL_OPTICAL_CHANGE],
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-66.01, 18.32],
                    [-66.01, 18.33],
                    [-66.00, 18.33],
                    [-66.00, 18.32],
                    [-66.01, 18.32],
                ]
            ],
        },
        change_start="2024-06-01",
        confidence=44.0,
    )


def test_export_writes_requested_layers(tmp_path):
    obs = _observation()
    res = exports.export_layers(
        str(tmp_path), aois=active_aois(), observations=[obs], change_candidates=[obs]
    )
    assert set(res["layers_written"]) == {
        "rm_monitoring_aois",
        "rm_observations",
        "rm_change_candidates",
    }
    for path in res["layers_written"].values():
        assert (tmp_path / path.split("/")[-1]).exists()


def test_features_carry_meta_block(tmp_path):
    obs = _observation()
    exports.export_layers(str(tmp_path), observations=[obs])
    fc = json.loads((tmp_path / "rm_observations.geojson").read_text())
    props = fc["features"][0]["properties"]
    assert "_meta" in props
    assert props["_meta"]["producer_module"] == exports.PRODUCER_MODULE


def test_manifest_has_reproducibility_block(tmp_path):
    exports.export_layers(str(tmp_path), aois=active_aois())
    manifest = json.loads((tmp_path / "rm_manifest.json").read_text())
    assert "reproducibility" in manifest
    for key in ("timestamp_utc", "repo_commit", "command"):
        assert key in manifest["reproducibility"]


def test_adjudication_and_crosswalk_layers_export(tmp_path):
    obs = _observation()
    obs.signals.append(schemas.SIGNAL_FIELD_CONFIRMATION)
    ev = adjudicate(obs, schemas.DECISION_CONFIRM, analyst_or_rule="analyst:jl")
    cw = PhysicalContractCrosswalk(
        observation_uid=obs.observation_uid,
        contract_node_uid="ms:node:1",
        observed_signal=None,
    )
    reconcile(cw, observable=True)
    res = exports.export_layers(str(tmp_path), adjudications=[ev], crosswalks=[cw])
    assert set(res["layers_written"]) == {"rm_adjudications", "rm_contract_crosswalk"}
    adj = json.loads((tmp_path / "rm_adjudications.geojson").read_text())
    assert adj["features"][0]["properties"]["decision"] == "confirm"
