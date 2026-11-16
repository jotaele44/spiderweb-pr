"""Deterministic construction of the committed registry documents.

Inputs are files that already live in this repository:

* ``configs/access_point_seeds.yaml`` -- operator-supplied provisional labels;
* ``configs/access_point_legacy_crosswalk.yaml`` -- explicit rules for reading
  the legacy node registry (which is never modified);
* the Guayama-Punta Tuna source-denominator receipt under ``evidence/marine``;
* the source catalogue of the current metadata-discovery run, if one is
  committed under ``evidence/access_points/source_discovery``.

Nothing is fetched, nothing is inferred from a name, and no coordinate is
produced that an input file does not state.  A discovery catalogue adds
sources that can be cited; it never adds or changes a feature.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from gebco.marine_evidence import CoverageState, ProductStage, SensorType

from .acquisition import PROVIDERS, to_source_manifestation
from .discovery import (
    DISCOVERY_DIR,
    POINTER_NAME,
    catalogue_rows,
    current_catalogue_path,
    load_catalogue,
)
from .models import (
    HORIZONTAL_INTERCHANGE_CRS,
    EvidenceAssertion,
    Observation,
    SourceManifestation,
)
from .namespaces import (
    IdentifierKind,
    Namespace,
    TypedRef,
    classify_identifier,
    observation_id,
    source_id,
)
from .registry import AccessPointRegistry
from .relationships import RelationshipLedger, spatial_adjacency
from .vertical import is_placeholder
from .vocabulary import (
    ClaimClass,
    EvidenceDimension,
    EvidenceTier,
    GeometryBasis,
    ProvenanceState,
)

PRODUCER_IDENTITY = "spiderweb-pr:spiderweb.access_points.seeding"
SEEDS_PATH = "configs/access_point_seeds.yaml"
CROSSWALK_PATH = "configs/access_point_legacy_crosswalk.yaml"
GUAYAMA_RECEIPT_PATH = (
    "evidence/marine/guayama_punta_tuna_v0_1/source_denominator_receipt.json"
)
REGISTRY_DIR = "registry/access_points"
ADJACENCY_THRESHOLD_M = 2000.0


class SeedingError(ValueError):
    """An input file is missing, malformed or asks for something not allowed."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> Mapping[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise SeedingError(f"{path} must contain a mapping")
    return data


def seed_offshore(
    registry: AccessPointRegistry, config: Mapping[str, Any]
) -> list[str]:
    """Register provisional labels as locality-only discovery observations."""

    if config.get("registry") != registry.namespace.value:
        raise SeedingError("seed file targets a different registry")
    stamp = str(config["generated_utc"])
    source_cfg = config["source"]
    created: list[str] = []
    for seed in config["seeds"]:
        forbidden = set(seed) - {"label", "locality"}
        if forbidden:
            raise SeedingError(
                f"seed {seed.get('label')!r} carries {sorted(forbidden)}; a provisional seed "
                "holds a label and a locality only -- register a source for anything else"
            )
        label = str(seed["label"])
        found = classify_identifier(label)
        if (
            found is None
            or found.kind is not IdentifierKind.PROVISIONAL_LABEL
            or found.namespace is not registry.namespace
        ):
            raise SeedingError(f"{label!r} is not a provisional label of this registry")
        source = SourceManifestation(
            source_id=source_id(str(source_cfg["provider"]), label, None, None),
            provider=str(source_cfg["provider"]),
            title=f"{label}: {source_cfg['note']}",
            native_identifier=label,
            product_stage=ProductStage.VISUALIZATION,
            sensor_type=SensorType.VISUALIZATION,
            coverage_state=CoverageState.UNKNOWN,
            provenance_state=ProvenanceState(str(source_cfg["provenance_state"])),
        )
        if source.provenance_state is not ProvenanceState.UNREGISTERED:
            raise SeedingError(
                "seed sources are UNREGISTERED until their files are attached"
            )
        registry.add_source(source)
        observation = Observation(
            observation_id=observation_id(registry.namespace, source.source_id, label),
            namespace=registry.namespace,
            source_id=source.source_id,
            native_record_id=label,
            geometry_basis=GeometryBasis.LOCALITY_LABEL_ONLY,
            raw_label=label,
            raw_attributes={"locality": str(seed["locality"])},
            discovered_utc=stamp,
            claim_class=ClaimClass.HYPOTHESIS,
            locality_label=str(seed["locality"]),
        )
        registry.add_observation(observation)
        feature = registry.register_candidate(
            "UNCLASSIFIED_ANOMALY",
            observation_ids=(observation.observation_id,),
            assertions=(
                EvidenceAssertion(
                    dimension=EvidenceDimension.EXISTENCE,
                    tier=EvidenceTier.CANDIDATE,
                    claim_class=ClaimClass.HYPOTHESIS,
                    basis=("screenshot_annotation",),
                    statement=(
                        f"operator annotated a location near {seed['locality']} on a screenshot "
                        "that has not been registered"
                    ),
                    observation_ids=(observation.observation_id,),
                    source_ids=(source.source_id,),
                ),
            ),
            provisional_labels=(label,),
            created_utc=stamp,
            notes=(
                "Provisional discovery only. No coordinates, depth, opening or connection is "
                "recorded because no registered source states one."
            ),
        )
        created.append(feature.feature_id)
    return created


@dataclass(frozen=True, slots=True)
class CrosswalkResult:
    legacy_nodes_read: int
    matched: int
    skipped_without_subtype: int
    skipped_without_coordinates: int
    skipped_unmatched: int
    feature_ids: tuple[str, ...]

    def closes(self) -> bool:
        return (
            self.matched
            + self.skipped_without_subtype
            + self.skipped_without_coordinates
            + self.skipped_unmatched
            == self.legacy_nodes_read
        )


def crosswalk_legacy(
    registries: Mapping[Namespace, AccessPointRegistry],
    config: Mapping[str, Any],
    repo_root: Path,
) -> CrosswalkResult:
    """Read the legacy node registry through explicit (type, subtype) rules."""

    legacy_rel = str(config["legacy_file"])
    legacy_path = repo_root / legacy_rel
    legacy = _load_yaml(legacy_path)
    stamp = str(config["generated_utc"])
    rules = {
        (str(r["legacy_type"]), str(r["legacy_subtype"])): (
            Namespace(str(r["registry"])),
            str(r["feature_class"]),
        )
        for r in config["rules"]
    }
    nodes = list(legacy.get("ilap_nodes") or [])
    ids = [str(n.get("node_id")) for n in nodes]
    if len(ids) != len(set(ids)):
        raise SeedingError("legacy registry holds duplicate node ids")

    upstream_files = sorted(
        {
            str(n["source_file"])
            for n in nodes
            if n.get("source_file")
            and (str(n.get("ilap_type")), str(n.get("ilap_subtype"))) in rules
        }
    )
    parents = [
        SourceManifestation(
            source_id=source_id("OPERATOR_LOCAL_DATASET", name, None, None),
            provider="OPERATOR_LOCAL_DATASET",
            title=f"{name} (operator-local input of the legacy registry; not in this repository)",
            native_identifier=name,
            provenance_state=ProvenanceState.UNREGISTERED,
        )
        for name in upstream_files
    ]
    legacy_source = SourceManifestation(
        source_id=source_id(
            "SPIDERWEB_LEGACY_NODE_REGISTRY", legacy_rel, None, _sha256(legacy_path)
        ),
        provider="SPIDERWEB_LEGACY_NODE_REGISTRY",
        title=f"{legacy_rel} ({legacy.get('version')}), legacy analytic node compilation",
        native_identifier=legacy_rel,
        manifestation_sha256=_sha256(legacy_path),
        retrieved_utc=stamp,
        published_date=(
            str(legacy.get("generated_at")) if legacy.get("generated_at") else None
        ),
        parent_source_ids=tuple(p.source_id for p in parents),
        product_stage=ProductStage.DERIVED_PRODUCT,
        coverage_state=CoverageState.UNKNOWN,
        provenance_state=ProvenanceState.REGISTERED,
    )
    for registry in registries.values():
        for parent in parents:
            registry.add_source(parent)
        registry.add_source(legacy_source)

    matched = no_subtype = no_coords = unmatched = 0
    created: list[str] = []
    for node in sorted(nodes, key=lambda n: str(n.get("node_id"))):
        if node.get("ilap_subtype") in (None, ""):
            no_subtype += 1
            continue
        key = (str(node.get("ilap_type")), str(node.get("ilap_subtype")))
        if key not in rules:
            unmatched += 1
            continue
        lat, lon = node.get("lat"), node.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            no_coords += 1
            continue
        namespace, feature_class = rules[key]
        registry = registries[namespace]
        node_id = str(node["node_id"])
        observation = Observation(
            observation_id=observation_id(namespace, legacy_source.source_id, node_id),
            namespace=namespace,
            source_id=legacy_source.source_id,
            native_record_id=node_id,
            geometry_basis=GeometryBasis.SOURCE_DIGITIZED,
            raw_label=str(node.get("name")) if node.get("name") else None,
            raw_attributes={
                **{str(k): v for k, v in node.items()},
                "legacy_namespace": str(config["legacy_namespace"]),
                "source_crs_declared": None,
                "horizontal_crs_basis": "ASSUMED_WGS84_UNDECLARED_IN_SOURCE",
            },
            geometry={"type": "Point", "coordinates": [float(lon), float(lat)]},
            horizontal_crs=HORIZONTAL_INTERCHANGE_CRS,
            horizontal_uncertainty_m=None,
            discovered_utc=stamp,
            claim_class=ClaimClass.ASSUMPTION,
        )
        registry.add_observation(observation)
        feature = registry.register_candidate(
            feature_class,
            observation_ids=(observation.observation_id,),
            assertions=(
                EvidenceAssertion(
                    dimension=EvidenceDimension.EXISTENCE,
                    tier=EvidenceTier.CANDIDATE,
                    claim_class=ClaimClass.ASSUMPTION,
                    basis=("legacy_registry_listing",),
                    statement=(
                        f"legacy registry lists node {node_id} of type {key[0]} / {key[1]}; "
                        "its coordinate reference system is not declared (WGS84 assumed) and "
                        "its positional accuracy is unknown"
                    ),
                    observation_ids=(observation.observation_id,),
                    source_ids=(legacy_source.source_id,),
                ),
            ),
            raw_names=(str(node["name"]),) if node.get("name") else (),
            created_utc=stamp,
            notes=(
                f"Crosswalked from legacy node {node_id} ({config['legacy_namespace']}). "
                "Coastal side not tested: no coastline version is registered."
            ),
        )
        created.append(feature.feature_id)
        matched += 1
    result = CrosswalkResult(
        len(nodes), matched, no_subtype, no_coords, unmatched, tuple(created)
    )
    if not result.closes():
        raise SeedingError("legacy crosswalk counts do not close")
    return result


def register_discovered_sources(
    registries: Mapping[Namespace, AccessPointRegistry], catalogue: Mapping[str, Any]
) -> dict[str, Any]:
    """Register what a metadata-discovery run listed, as references only.

    A source goes into a registry only if a search box of that registry listed
    it.  Every one is ``REFERENCED_ONLY`` with unknown coverage: it can be
    cited, it cannot satisfy a direct-observation gate, and registering it
    touches no feature.
    """

    counts = {namespace.value: 0 for namespace in sorted(registries)}
    for provider_id, namespaces, row in catalogue_rows(catalogue):
        spec = PROVIDERS[provider_id]
        manifestation = to_source_manifestation(spec, row)
        for namespace in namespaces:
            if namespace not in registries:
                raise SeedingError(
                    f"catalogue names a registry that is not being built: {namespace}"
                )
            if namespace not in spec.serves:
                raise SeedingError(
                    f"{provider_id} does not serve {namespace.value}; catalogue is inconsistent"
                )
            if registries[namespace].add_source(manifestation):
                counts[namespace.value] += 1
    stated = catalogue["totals"]["sources_by_namespace"]
    if {k: v for k, v in counts.items() if v} != dict(stated):
        raise SeedingError(
            "discovery catalogue totals do not match the sources it lists"
        )
    return {
        "run_id": catalogue["run_id"],
        "discovered_utc": catalogue["discovered_utc"],
        "catalogue_content_sha256": catalogue["content_sha256"],
        "registered": counts,
    }


_GUAYAMA_TITLE = "listed in the Guayama-Punta Tuna v0.1 source-denominator receipt"


def register_guayama_sources(
    registry: AccessPointRegistry, receipt_path: Path
) -> dict[str, int]:
    """Register the surveys named by the committed Guayama receipt as references.

    These are catalogue and inventory listings.  Their data products are not
    held, so every one is ``REFERENCED_ONLY`` with unknown coverage.  The
    vertical-datum strings the inventory published are counted as stated.

    A survey the registry already holds from a later discovery run (same
    provider, same native identifier) is counted as ``already_registered`` and
    not added a second time, so one survey never appears as two sources.
    """

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    counts = {
        "multibeam": 0,
        "sounding": 0,
        "bag": 0,
        "topobathy_lidar": 0,
        "datum_placeholders": 0,
        "already_registered": 0,
        "added": 0,
    }
    held = {(s.provider, s.native_identifier) for s in registry.sources.values()}

    def add(
        provider: str,
        native: str,
        title: str,
        sensor: SensorType,
        survey: str | None = None,
    ) -> None:
        if (provider, native) in held:
            counts["already_registered"] += 1
            return
        counts["added"] += 1
        registry.add_source(
            SourceManifestation(
                source_id=source_id(provider, native, None, None),
                provider=provider,
                title=f"{title} ({_GUAYAMA_TITLE})",
                native_identifier=native,
                survey_date=survey,
                lineage_root_id=native,
                product_stage=ProductStage.DERIVED_PRODUCT,
                sensor_type=sensor,
                coverage_state=CoverageState.UNKNOWN,
                provenance_state=ProvenanceState.REFERENCED_ONLY,
                license_note="US_GOVERNMENT_PUBLIC_DOMAIN",
            )
        )

    for survey in receipt["ncei_multibeam_survey_ids"]:
        add(
            "NCEI_MULTIBEAM_CATALOG",
            f"NCEI:multibeam:{survey}",
            str(survey),
            SensorType.MULTIBEAM_ECHOSOUNDER,
        )
        counts["multibeam"] += 1
    for survey in receipt["ncei_sounding_survey_ids"]:
        add(
            "NCEI_SOUNDING_CATALOG",
            f"NCEI:sounding:{survey}",
            str(survey),
            SensorType.HYDROGRAPHIC_SOUNDINGS,
        )
        counts["sounding"] += 1
    for survey in receipt["nos_bag_survey_ids"]:
        add(
            "NOS_BAG_INVENTORY",
            f"NOS:BAG:{survey}",
            str(survey),
            SensorType.MULTIBEAM_ECHOSOUNDER,
        )
        counts["bag"] += 1
    for feature in receipt["usiei_topobathy_features"]:
        add(
            "USIEI_TOPOBATHY_LIDAR",
            f"USIEI:GlobalID:{feature['globalid']}",
            str(feature["project_name"]),
            SensorType.TOPOBATHYMETRIC_LIDAR,
            feature.get("collection_date"),
        )
        counts["topobathy_lidar"] += 1
        if is_placeholder(feature.get("vertical_datum")):
            counts["datum_placeholders"] += 1
    expected = receipt["live_counts"]
    if (
        counts["multibeam"] != expected["ncei_multibeam_surveys"]
        or counts["sounding"] != expected["ncei_sounding_surveys"]
        or counts["bag"] != expected["nos_bag_surveys"]
        or counts["topobathy_lidar"] != expected["usiei_topobathy_features"]
    ):
        raise SeedingError("Guayama receipt lists do not match its own stated counts")
    return counts


def _point_of(
    registry: AccessPointRegistry, feature_id: str
) -> tuple[float, float] | None:
    feature = registry.feature(feature_id)
    for oid in feature.observation_ids:
        geometry = registry.observations[oid].geometry
        if geometry and geometry.get("type") == "Point":
            lon, lat = geometry["coordinates"][:2]
            return float(lon), float(lat)
    return None


def adjacency_ledger(
    inland: AccessPointRegistry, offshore: AccessPointRegistry, *, threshold_m: float
) -> RelationshipLedger:
    """Inland-to-off-shore pairs within a distance.  Discovery, not connection."""

    ledger = RelationshipLedger(producer_identity=PRODUCER_IDENTITY)
    for inland_id in sorted(inland.features):
        a = _point_of(inland, inland_id)
        if a is None:
            continue
        for offshore_id in sorted(offshore.features):
            b = _point_of(offshore, offshore_id)
            if b is None:
                continue
            relationship = spatial_adjacency(
                TypedRef(inland.namespace, inland_id),
                a,
                TypedRef(offshore.namespace, offshore_id),
                b,
                threshold_m=threshold_m,
            )
            if relationship is not None:
                ledger.add(relationship)
    return ledger


@dataclass(frozen=True)
class BuildResult:
    inland: AccessPointRegistry
    offshore: AccessPointRegistry
    ledger: RelationshipLedger
    crosswalk: CrosswalkResult
    seeded: tuple[str, ...]
    guayama: Mapping[str, int]
    input_hashes: Mapping[str, str]
    discovery: Mapping[str, Any] | None = None


def build_all(repo_root: str | Path) -> BuildResult:
    root = Path(repo_root)
    seeds = _load_yaml(root / SEEDS_PATH)
    crosswalk_cfg = _load_yaml(root / CROSSWALK_PATH)
    inland = AccessPointRegistry(
        Namespace.ACCESS_POINT_INLAND, producer_identity=PRODUCER_IDENTITY
    )
    offshore = AccessPointRegistry(
        Namespace.ACCESS_POINT_OFFSHORE, producer_identity=PRODUCER_IDENTITY
    )
    seeded = seed_offshore(offshore, seeds)
    crosswalk = crosswalk_legacy(
        {
            Namespace.ACCESS_POINT_INLAND: inland,
            Namespace.ACCESS_POINT_OFFSHORE: offshore,
        },
        crosswalk_cfg,
        root,
    )
    discovery = None
    discovery_inputs: list[str] = []
    catalogue_path = current_catalogue_path(root / DISCOVERY_DIR)
    if catalogue_path is not None:
        discovery = register_discovered_sources(
            {
                Namespace.ACCESS_POINT_INLAND: inland,
                Namespace.ACCESS_POINT_OFFSHORE: offshore,
            },
            load_catalogue(catalogue_path),
        )
        discovery_inputs = [
            f"{DISCOVERY_DIR}/{POINTER_NAME}",
            catalogue_path.relative_to(root).as_posix(),
        ]
    guayama = register_guayama_sources(offshore, root / GUAYAMA_RECEIPT_PATH)
    ledger = adjacency_ledger(inland, offshore, threshold_m=ADJACENCY_THRESHOLD_M)
    inputs = {
        rel: _sha256(root / rel)
        for rel in (
            SEEDS_PATH,
            CROSSWALK_PATH,
            str(crosswalk_cfg["legacy_file"]),
            GUAYAMA_RECEIPT_PATH,
            *discovery_inputs,
        )
    }
    return BuildResult(
        inland, offshore, ledger, crosswalk, tuple(seeded), guayama, inputs, discovery
    )


def write_documents(result: BuildResult, repo_root: str | Path) -> dict[str, str]:
    """Write the three registry documents and a build manifest; return hashes."""

    out = Path(repo_root) / REGISTRY_DIR
    out.mkdir(parents=True, exist_ok=True)
    documents = {
        "inland.json": result.inland.to_document(),
        "offshore.json": result.offshore.to_document(),
        "relationships.json": result.ledger.to_document(),
    }
    hashes: dict[str, str] = {}
    for name, document in documents.items():
        text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        (out / name).write_text(text, encoding="utf-8")
        hashes[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    manifest = {
        "schema": "access_point_registry_build/1.0",
        "producer_identity": PRODUCER_IDENTITY,
        "inputs": dict(sorted(result.input_hashes.items())),
        "outputs": {
            name: {
                "sha256": digest,
                "content_sha256": documents[name]["content_sha256"],
            }
            for name, digest in sorted(hashes.items())
        },
        "counts": {
            "inland": result.inland.counts(),
            "offshore": result.offshore.counts(),
            "relationships": len(result.ledger.relationships),
            "legacy_crosswalk": {
                "legacy_nodes_read": result.crosswalk.legacy_nodes_read,
                "matched": result.crosswalk.matched,
                "skipped_without_subtype": result.crosswalk.skipped_without_subtype,
                "skipped_without_coordinates": result.crosswalk.skipped_without_coordinates,
                "skipped_unmatched": result.crosswalk.skipped_unmatched,
                "closes": result.crosswalk.closes(),
            },
            "provisional_seeds": len(result.seeded),
            "guayama_reference_sources": dict(result.guayama),
            "live_discovery": (
                None if result.discovery is None else dict(result.discovery)
            ),
        },
    }
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (out / "build_manifest.json").write_text(text, encoding="utf-8")
    hashes["build_manifest.json"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashes
