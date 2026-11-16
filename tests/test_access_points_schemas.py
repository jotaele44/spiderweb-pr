"""Schema controls for the access-point documents."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from gebco.marine_evidence import CoverageState, ProductStage, SensorType  # noqa: E402
from integration.schema_validation import SchemaValidator  # noqa: E402
from spiderweb.access_points import namespaces as ns  # noqa: E402
from spiderweb.access_points import relationships as rel  # noqa: E402
from spiderweb.access_points import vocabulary as v  # noqa: E402
from tests import access_points_support as sup  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
NAMES = [
    "access_point_registry",
    "access_point_relationship_ledger",
    "access_point_certification_report",
]


def schema(name: str) -> dict:
    return json.loads((REPO / "schemas" / f"{name}.schema.json").read_text())


def errors(name: str, instance) -> list[str]:
    return [
        e.message
        for e in jsonschema.Draft7Validator(schema(name)).iter_errors(instance)
    ]


def values(enum_cls) -> list:
    return [member.value for member in enum_cls]


@pytest.mark.parametrize("name", NAMES)
def test_schema_is_valid_named_without_reserved_tokens_and_discoverable(name):
    document = schema(name)
    jsonschema.Draft7Validator.check_schema(document)
    assert document["$id"] == name
    ns.validate_new_machine_identifier(name)
    assert name in SchemaValidator().available_schemas()


def test_committed_documents_conform():
    for name in ("inland.json", "offshore.json"):
        instance = json.loads((REPO / "registry" / "access_points" / name).read_text())
        assert errors("access_point_registry", instance) == []
    ledger = json.loads(
        (REPO / "registry" / "access_points" / "relationships.json").read_text()
    )
    assert errors("access_point_relationship_ledger", ledger) == []
    report = REPO / "evidence" / "access_points" / "certification_report_v1.json"
    if report.is_file():
        instance = json.loads(report.read_text())
        assert errors("access_point_certification_report", instance) == []
        assert instance["production_authorized"] is False
        assert instance["independent_review"]["performed"] is False


def _rich_registry_document() -> dict:
    registry, _, _, feature = sup.registry_with_direct_feature()
    registry.promote(feature.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    return registry.to_document()


def _rich_ledger_document() -> dict:
    ledger = rel.RelationshipLedger(producer_identity=sup.PRODUCER)
    source = sup.direct_source("TEST-ASBUILT-001")
    ledger.add_source(source)
    a = ns.TypedRef(sup.INLAND, "INAP-PR-000001")
    b = ns.TypedRef(sup.OFFSHORE, "OFAP-PR-000001")
    c = ns.TypedRef(sup.OFFSHORE, "OFAP-PR-000002")
    measured = rel.make_relationship(
        v.RelationshipType.MEASURED_HYDRAULIC_CONNECTION,
        a,
        b,
        claim_class=v.ClaimClass.FACT,
        tier=v.EvidenceTier.DIRECT,
        basis=("dye_trace",),
        statement="synthetic",
        source_ids=(source.source_id,),
    )
    ledger.add(rel.accept(measured, reviewer=sup.REVIEWER, utc=sup.UTC))
    ledger.add(
        rel.spatial_adjacency(
            a, (-66.1, 17.95), c, (-66.1005, 17.9495), threshold_m=500
        )
    )
    ledger.add(
        rel.make_relationship(
            v.RelationshipType.CONTRADICTORY_RELATIONSHIP,
            a,
            b,
            claim_class=v.ClaimClass.FACT,
            tier=v.EvidenceTier.DIRECT,
            basis=("dye_trace",),
            statement="tracer not recovered",
            source_ids=(source.source_id,),
            contradicts=(measured.relationship_id,),
        )
    )
    return ledger.to_document()


def test_rich_documents_conform():
    assert errors("access_point_registry", _rich_registry_document()) == []
    assert errors("access_point_relationship_ledger", _rich_ledger_document()) == []


def _mutate(document: dict, edit) -> dict:
    changed = copy.deepcopy(document)
    edit(changed)
    return changed


@pytest.mark.parametrize(
    "name, edit",
    [
        (
            "coordinates on a locality-only observation",
            lambda d: d["observations"][0].update(
                geometry={"type": "Point", "coordinates": [-67.2, 18.5]},
                horizontal_crs="OGC:CRS84",
            ),
        ),
        ("unknown status", lambda d: d["features"][0].update(status="CONFIRMED")),
        (
            "feature id of the other registry",
            lambda d: d["features"][0].update(feature_id="INAP-PR-000001"),
        ),
        (
            "legacy identifier as a feature id",
            lambda d: d["features"][0].update(feature_id="ILAP_AREA_X_001"),
        ),
        (
            "provisional label as a feature id",
            lambda d: d["features"][0].update(feature_id="OSAP-SEED-001"),
        ),
        (
            "inland class in the off-shore registry",
            lambda d: d["features"][0].update(feature_class="SINKHOLE"),
        ),
        ("extra property", lambda d: d["features"][0].update(depth_m=40)),
        ("extra top-level property", lambda d: d.update(reviewed=True)),
        ("legacy namespace", lambda d: d.update(namespace="aviation.ilap_path")),
        ("bad hash", lambda d: d.update(content_sha256="abc")),
        (
            "counts without a status bucket",
            lambda d: d["counts"]["features_by_status"].pop("VERIFIED"),
        ),
    ],
)
def test_registry_schema_rejects(name, edit):
    committed = json.loads(
        (REPO / "registry" / "access_points" / "offshore.json").read_text()
    )
    assert errors("access_point_registry", committed) == []
    assert errors("access_point_registry", _mutate(committed, edit)), name


@pytest.mark.parametrize(
    "name, edit",
    [
        (
            "registered source without a hash",
            lambda d: d["sources"][0].update(manifestation_sha256=None),
        ),
        (
            "value without a vertical reference",
            lambda d: d["observations"][0].update(value_m=12.0),
        ),
        (
            "stored geometry in another CRS",
            lambda d: d["observations"][0].update(horizontal_crs="EPSG:32620"),
        ),
        (
            "accepted assertion without a reviewer",
            lambda d: d["features"][0]["assertions"][0].update(adjudicated_by=None),
        ),
        (
            "connectivity assertion without a kind",
            lambda d: d["features"][0]["assertions"][0].update(
                dimension="CONNECTIVITY", connectivity_kind=None
            ),
        ),
        (
            "unknown tier",
            lambda d: d["features"][0]["assertions"][0].update(tier="CERTAIN"),
        ),
    ],
)
def test_registry_schema_rejects_evidence_shortcuts(name, edit):
    document = _rich_registry_document()
    assert errors("access_point_registry", _mutate(document, edit)), name


@pytest.mark.parametrize(
    "name, edit",
    [
        (
            "contradiction naming nothing",
            lambda d: [
                r
                for r in d["relationships"]
                if r["relationship_type"] == "CONTRADICTORY_RELATIONSHIP"
            ][0].update(contradicts=[]),
        ),
        (
            "unknown relationship type",
            lambda d: d["relationships"][0].update(relationship_type="CONNECTED"),
        ),
        (
            "unknown namespace on an end",
            lambda d: d["relationships"][0]["source"].update(namespace="ilap"),
        ),
        ("negative distance", lambda d: d["relationships"][0].update(distance_m=-1)),
        ("extra property", lambda d: d["relationships"][0].update(verified=True)),
    ],
)
def test_ledger_schema_rejects(name, edit):
    assert errors(
        "access_point_relationship_ledger", _mutate(_rich_ledger_document(), edit)
    ), name


def test_schema_vocabularies_cannot_drift_from_the_code():
    registry = schema("access_point_registry")["properties"]
    feature = registry["features"]["items"]["properties"]
    assertion = feature["assertions"]["items"]["properties"]
    source = registry["sources"]["items"]["properties"]
    observation = registry["observations"]["items"]["properties"]
    assert feature["status"]["enum"] == values(v.RegistryStatus)
    assert set(feature["feature_class"]["enum"]) == set(
        values(v.InlandFeatureClass)
    ) | set(values(v.OffshoreFeatureClass))
    assert assertion["dimension"]["enum"] == values(v.EvidenceDimension)
    assert assertion["tier"]["enum"] == [t.name for t in v.EvidenceTier]
    assert assertion["claim_class"]["enum"] == values(v.ClaimClass)
    assert assertion["adjudication"]["enum"] == values(v.AdjudicationStatus)
    assert source["provenance_state"]["enum"] == values(v.ProvenanceState)
    assert source["product_stage"]["enum"] == values(ProductStage)
    assert source["coverage_state"]["enum"] == values(CoverageState)
    assert source["sensor_type"]["enum"] == values(SensorType) + [None]
    assert observation["geometry_basis"]["enum"] == values(v.GeometryBasis)
    assert set(registry["namespace"]["enum"]) == {
        n.value for n in ns.REGISTRY_NAMESPACES
    }
    ledger = schema("access_point_relationship_ledger")["properties"]["relationships"][
        "items"
    ]["properties"]
    assert ledger["relationship_type"]["enum"] == values(v.RelationshipType)
    assert ledger["source"]["properties"]["namespace"]["enum"] == values(ns.Namespace)
    report = schema("access_point_certification_report")["properties"]
    gate = report["gates"]["items"]["properties"]
    assert gate["state"]["enum"] == [
        "PASS",
        "FAIL",
        "OPEN",
        "BLOCKED",
        "PROVISIONAL",
        "UNRESOLVED",
    ]
    assert gate["claim_class"]["enum"] == values(v.ClaimClass)


def _report(**overrides) -> dict:
    readiness = {
        k: {"state": "OPEN", "statement": "synthetic"}
        for k in ("engineering", "science", "gui", "federation", "production")
    }
    document = {
        "schema": "access_point_certification_report/1.0",
        "generated_utc": sup.UTC,
        "repositories": [{"repo": "spiderweb-pr", "head_sha": "a" * 40}],
        "gates": [
            {
                "gate_id": "TESTS",
                "title": "tests",
                "state": "PASS",
                "claim_class": "COMPUTED",
                "evidence": ["x"],
                "detail": "synthetic",
            }
        ],
        "readiness": readiness,
        "scores": [
            {
                "dimension": "overall",
                "verified": 10,
                "projected": 20,
                "basis": "synthetic",
            }
        ],
        "artifacts": [{"path": "x", "sha256": "b" * 64}],
        "independent_review": {
            "performed": False,
            "reviewer": None,
            "statement": "not performed",
        },
        "production_authorized": False,
    }
    document.update(overrides)
    return document


def test_certification_report_cannot_claim_what_did_not_happen():
    assert errors("access_point_certification_report", _report()) == []
    # No independent review: production cannot be authorised or reported ready.
    assert errors(
        "access_point_certification_report", _report(production_authorized=True)
    )
    ready = _report()
    ready["readiness"]["production"]["state"] = "PASS"
    assert errors("access_point_certification_report", ready)
    for bad in (
        {"gates": [{**_report()["gates"][0], "state": "CERTIFIED"}]},
        {"gates": [{**_report()["gates"][0], "claim_class": "PROVEN"}]},
        {
            "scores": [
                {"dimension": "x", "verified": 120, "projected": 10, "basis": "y"}
            ]
        },
        {"repositories": [{"repo": "x", "head_sha": "abc"}]},
        {"independent_review": {"performed": False, "reviewer": None, "statement": ""}},
    ):
        assert errors("access_point_certification_report", _report(**bad)), bad
