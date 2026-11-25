"""Exporting access-point registry records to the federation hub (V13)."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from spiderweb.access_points import hub_export as hx
from spiderweb.access_points import models as m
from spiderweb.access_points import namespaces as ns
from spiderweb.access_points import vocabulary as v
from spiderweb.access_points.registry import AccessPointRegistry
from tests import access_points_support as sup

REPO = Path(__file__).resolve().parents[1]
jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("prii_export_utils")


def _export_module():
    spec = importlib.util.spec_from_file_location(
        "federation_export_under_test", REPO / "scripts" / "federation_export.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FX = _export_module()
NOW = "2026-11-20T00:00:00Z"


def lane(registry_dir):
    return FX.build_access_point_lane(Path(registry_dir), NOW)


def _schema(name):
    return json.loads((REPO / "schemas" / f"federation_{name}.schema.json").read_text())


def test_the_committed_registries_export_candidates_only_and_validate():
    out = lane(REPO / "registry" / "access_points")
    for stream, schema in (
        ("sources", "source"),
        ("entities", "entity"),
        ("relationships", "relationship"),
    ):
        validator = jsonschema.Draft202012Validator(_schema(schema))
        for row in out[stream]:
            assert not list(validator.iter_errors(row)), row
    records = [
        e for e in out["entities"] if e["entity_type"] in hx.ENTITY_TYPE.values()
    ]
    assert len(records) == 5
    assert {r["attributes"]["status"] for r in records} == {"CANDIDATE"}
    for row in records:
        state = row["evidence_state"]
        assert state["identity_state"] == "CANDIDATE"
        assert state["identity_scope"] == "PRODUCER_LOCAL"
        assert state["epistemic_class"] == "INTERPRETIVE"
        assert row["synthetic"] is False
        assert row["confidence"] == hx.STATUS_CONFIDENCE[v.RegistryStatus.CANDIDATE]
        assert row["attributes"]["identity_default"] == "CANDIDATE_NOT_IDENTITY"
        if "location" in row:
            assert state["geometry_precision"] == "REPRESENTATIVE_POINT"
            assert state["coordinate_method"] == hx.CRS_ASSUMED_METHOD
    summary = out["summary"]["registries"]
    assert summary["access_point.offshore"]["withheld_by_status"] == {
        "PROVISIONAL_DISCOVERY": 5
    }
    # Every record points to its registry and nowhere else.
    registries = {
        e["entity_id"]
        for e in out["entities"]
        if e["entity_type"] == hx.REGISTRY_ENTITY_TYPE
    }
    assert len(registries) == 2
    assert len(out["relationships"]) == 5
    for rel in out["relationships"]:
        assert rel["relationship_type"] == "reported_by"
        assert rel["target_entity_id"] in registries
    # The same input gives the same ids.
    again = lane(REPO / "registry" / "access_points")
    assert [e["entity_id"] for e in again["entities"]] == [
        e["entity_id"] for e in out["entities"]
    ]


def _write(tmp_path, inland: AccessPointRegistry, offshore: AccessPointRegistry):
    for registry, name in ((inland, "inland.json"), (offshore, "offshore.json")):
        (tmp_path / name).write_text(
            json.dumps(registry.to_document()), encoding="utf-8"
        )
    return tmp_path


def test_status_decides_export_and_only_a_stated_point_becomes_a_location(tmp_path):
    inland = AccessPointRegistry(sup.INLAND, producer_identity=sup.PRODUCER)
    source = sup.direct_source()
    inland.add_source(source)
    with_point = sup.point_observation(sup.INLAND, source, "P1", lon=-66.5, lat=18.2)
    no_point = m.Observation(
        observation_id=ns.observation_id(sup.INLAND, source.source_id, "P2"),
        namespace=sup.INLAND,
        source_id=source.source_id,
        native_record_id="P2",
        geometry_basis=v.GeometryBasis.LOCALITY_LABEL_ONLY,
        locality_label="somewhere in Utuado",
    )
    rejected_obs = sup.point_observation(sup.INLAND, source, "P3")
    for obs in (with_point, no_point, rejected_obs):
        inland.add_observation(obs)
    existence = sup.assertion(
        v.EvidenceDimension.EXISTENCE, v.EvidenceTier.CANDIDATE, source
    )
    a = inland.register_candidate(
        "SINKHOLE",
        observation_ids=(with_point.observation_id,),
        assertions=(existence,),
        created_utc=sup.UTC,
    )
    b = inland.register_candidate(
        "SINKHOLE",
        observation_ids=(no_point.observation_id,),
        assertions=(existence,),
        created_utc=sup.UTC,
    )
    c = inland.register_candidate(
        "SINKHOLE",
        observation_ids=(rejected_obs.observation_id,),
        assertions=(existence,),
        created_utc=sup.UTC,
    )
    inland.set_status(c.feature_id, v.RegistryStatus.REJECTED, utc=sup.UTC)
    offshore = AccessPointRegistry(sup.OFFSHORE, producer_identity=sup.PRODUCER)
    out = lane(_write(tmp_path, inland, offshore))
    rows = {
        e["attributes"]["feature_id"]: e
        for e in out["entities"]
        if e["entity_type"] == "inland_access_point"
    }
    assert set(rows) == {a.feature_id, b.feature_id}
    assert rows[a.feature_id]["location"] == {"lat": 18.2, "lon": -66.5}
    assert rows[a.feature_id]["evidence_state"]["coordinate_method"] == (
        "REGISTRY_OBSERVATION_POINT_MEASURED"
        if "MEASURED" in hx.POINT_METHOD
        else "REGISTRY_OBSERVATION_POINT"
    )
    assert "location" not in rows[b.feature_id]
    assert "geometry_precision" not in rows[b.feature_id]["evidence_state"]
    assert out["summary"]["registries"]["access_point.inland"][
        "withheld_by_status"
    ] == {"REJECTED": 1}


def test_a_registry_document_that_fails_its_hash_stops_the_export(tmp_path):
    for name in ("inland.json", "offshore.json"):
        shutil.copy(REPO / "registry" / "access_points" / name, tmp_path / name)
    document = json.loads((tmp_path / "inland.json").read_text())
    document["features"][0]["feature_class"] = "CAVE_ENTRANCE"
    (tmp_path / "inland.json").write_text(json.dumps(document))
    with pytest.raises(hx.AccessPointExportError, match="inland.json"):
        lane(tmp_path)
    (tmp_path / "offshore.json").unlink()
    shutil.copy(
        REPO / "registry" / "access_points" / "inland.json", tmp_path / "inland.json"
    )
    with pytest.raises(hx.AccessPointExportError, match="missing"):
        lane(tmp_path)
    # A registry file in the other's place is refused.
    shutil.copy(
        REPO / "registry" / "access_points" / "inland.json", tmp_path / "offshore.json"
    )
    with pytest.raises(hx.AccessPointExportError, match="holds access_point.inland"):
        lane(tmp_path)


class _SteppingClock:
    """Stands in for the export script's ``datetime``: each run is a second later.

    Two runs of the export are never guaranteed to fall in the same second, so
    a test that compares their output must not depend on when they ran.
    """

    _tick = 0

    @classmethod
    def now(cls, tz=None):
        from datetime import datetime as real
        from datetime import timedelta

        cls._tick += 1
        return real(2026, 11, 20, 0, 0, 0, tzinfo=tz) + timedelta(seconds=cls._tick)


def _run(argv, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["federation_export.py", *argv])
    monkeypatch.setattr(FX, "datetime", _SteppingClock)
    code = FX.main()
    return code, capsys.readouterr()


def test_without_the_flag_the_package_is_unchanged_and_with_it_has_no_synthetic_rows(
    tmp_path, monkeypatch, capsys
):
    base = [
        "--package",
        str(REPO / "exports" / "real"),
        "--mode",
        "production",
        "--no-ppp-geometry",
    ]
    code, _ = _run([*base, "--out", str(tmp_path / "without")], monkeypatch, capsys)
    assert code == 0
    code, err = _run(
        [
            *base,
            "--out",
            str(tmp_path / "with"),
            "--access-point-registries",
            str(REPO / "registry" / "access_points"),
        ],
        monkeypatch,
        capsys,
    )
    assert code == 0 and "access points:" in err.err
    without = {
        f["stream"]: f["record_count"]
        for f in json.loads((tmp_path / "without" / "manifest.json").read_text())[
            "files"
        ]
    }
    with_lane = {
        f["stream"]: f["record_count"]
        for f in json.loads((tmp_path / "with" / "manifest.json").read_text())["files"]
    }
    assert with_lane["entities"] == without["entities"] + 7
    assert with_lane["sources"] == without["sources"] + 2
    assert with_lane["relationships"] == without["relationships"] + 5
    rows = [
        json.loads(line)
        for line in (tmp_path / "with" / "entities.jsonl").read_text().splitlines()
    ]
    assert not [r for r in rows if r.get("synthetic")]

    # Rows already in the package are unchanged by the lane, apart from the
    # time each run stamps on them (its manifest's created_at).
    def rows_without_run_time(folder):
        now = json.loads((folder / "manifest.json").read_text())["created_at"]
        out = {}
        for line in (folder / "entities.jsonl").read_text().splitlines():
            row = json.loads(line)
            assert row["extracted_at"] == now
            row.pop("extracted_at")
            if row.get("created_at") == now:
                row.pop("created_at")
            out[row["entity_id"]] = row
        return out

    before = rows_without_run_time(tmp_path / "without")
    after = rows_without_run_time(tmp_path / "with")
    assert {k: after[k] for k in before} == before


def test_a_broken_registry_fails_the_export_command(tmp_path, monkeypatch, capsys):
    shutil.copy(
        REPO / "registry" / "access_points" / "inland.json", tmp_path / "inland.json"
    )
    code, err = _run(
        [
            "--package",
            str(REPO / "exports" / "real"),
            "--mode",
            "production",
            "--no-ppp-geometry",
            "--out",
            str(tmp_path / "out"),
            "--access-point-registries",
            str(tmp_path),
        ],
        monkeypatch,
        capsys,
    )
    assert code == 2 and "not exportable" in err.err
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_the_canonical_command_carries_the_lane():
    manifest = json.loads((REPO / "federation.json").read_text())
    command = manifest["hub_callable_commands"]["export_canonical"]
    assert command.endswith("--access-point-registries registry/access_points")
    assert "--mode production" in command
