"""Read-only context from other producers' exported federation packages.

Other producers own their records.  This module reads a package they have
exported, verifies it, and exposes selected rows as *context* that an analyst
can place next to an access-point feature.  It is deliberately thin:

* it reads exported artefacts only -- no sibling source code is imported and
  no sibling database or service is called;
* a package is trusted only after its manifest closes: every listed file is
  present, hashes to the stated SHA-256 and holds the stated number of rows;
* foreign identifiers are kept verbatim as references.  Nothing is re-minted,
  merged into access-point identity, or correlated across producers -- that is
  the hub's job;
* a stream that a producer did not export is ``NOT_EXPORTED``, never "zero";
* context can never establish that something physically exists.  A contract,
  an award, a disbursement, an ownership record or a municipality name is
  documentary: it may accompany a candidate, and it cannot create one, locate
  one, or raise its evidence tier.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from federation.spatial_core import validate_lon_lat
from federation.spatial_relations import SpatialRelation, within_distance
from pipeline.path_safety import safe_join

from .models import EvidenceAssertion, SourceManifestation
from .namespaces import TypedRef
from .vocabulary import ClaimClass, EvidenceDimension, EvidenceTier

CONTEXT_VERSION = "access-point-federation-context/1.0"
SUPPORTED_CONTRACT_MAJOR = 1
EXPECTED_HUB_PARENT = "thehub-pr"

# Schema ids of the hub's canonical streams.  A package using any other set is
# a different contract and is refused rather than guessed at.
CANONICAL_SCHEMA_IDS: frozenset[str] = frozenset(
    {
        "federation_source.schema.json",
        "federation_entity.schema.json",
        "federation_relationship.schema.json",
        "federation_observation.schema.json",
        "federation_alert.schema.json",
        "federation_source_monitor.schema.json",
    }
)

# Directory names that hold producer fixtures.  Some are flagged
# ``synthetic: false`` and ``mode: production`` although they carry placeholder
# records, so they are refused by location, not by flag.
_FIXTURE_PATH_PARTS = frozenset({"samples", "conformance", "fixtures", "examples"})


class PackageIntegrityError(ValueError):
    """A federation package is missing, altered or not what it claims to be."""


class StreamState(StrEnum):
    PRESENT = "PRESENT"
    NOT_EXPORTED = "NOT_EXPORTED"


@dataclass(frozen=True)
class VerifiedPackage:
    producer: str
    contract_version: str
    package_id: str | None
    mode: str | None
    directory: str
    streams: Mapping[str, tuple[Mapping[str, Any], ...]]
    files: tuple[Mapping[str, Any], ...]
    synthetic_rows_dropped: int

    def stream_state(self, name: str) -> StreamState:
        return StreamState.PRESENT if name in self.streams else StreamState.NOT_EXPORTED

    def rows(self, name: str) -> tuple[Mapping[str, Any], ...]:
        """Rows of a stream.  Raises if the producer did not export it."""

        if name not in self.streams:
            raise PackageIntegrityError(
                f"{self.producer} did not export a {name!r} stream; that is not zero records"
            )
        return self.streams[name]


def load_package(
    directory: str | Path,
    *,
    expected_producer: str,
    allow_fixture: bool = False,
    accepted_schema_ids: frozenset[str] = CANONICAL_SCHEMA_IDS,
) -> VerifiedPackage:
    """Verify and load an exported federation package directory."""

    base = Path(directory)
    if not allow_fixture and _FIXTURE_PATH_PARTS & {
        part.lower() for part in base.parts
    }:
        raise PackageIntegrityError(
            f"{base} is a fixture or sample location and cannot be used as evidence"
        )
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        raise PackageIntegrityError(f"no manifest.json in {base}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackageIntegrityError(f"manifest.json is not valid JSON: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise PackageIntegrityError("manifest.json must be an object")

    producer = manifest.get("producer")
    if producer != expected_producer:
        raise PackageIntegrityError(
            f"package producer is {producer!r}, expected {expected_producer!r}"
        )
    version = str(manifest.get("export_contract_version", ""))
    try:
        major = int(version.split(".")[0])
    except ValueError:
        raise PackageIntegrityError(
            f"unreadable export_contract_version {version!r}"
        ) from None
    if major != SUPPORTED_CONTRACT_MAJOR:
        raise PackageIntegrityError(
            f"export_contract_version {version} is not supported (major {SUPPORTED_CONTRACT_MAJOR})"
        )
    federation = manifest.get("federation")
    if (
        not isinstance(federation, Mapping)
        or federation.get("hub_parent") != EXPECTED_HUB_PARENT
    ):
        raise PackageIntegrityError(
            "package is not a hub-canonical export (federation.hub_parent is not thehub-pr)"
        )
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise PackageIntegrityError("manifest lists no files")

    streams: dict[str, tuple[Mapping[str, Any], ...]] = {}
    dropped = 0
    for entry in files:
        if not isinstance(entry, Mapping):
            raise PackageIntegrityError("manifest file entry must be an object")
        name = entry.get("filename")
        stream = entry.get("stream")
        if not isinstance(name, str) or not isinstance(stream, str):
            raise PackageIntegrityError("manifest file entry needs filename and stream")
        if entry.get("schema_id") not in accepted_schema_ids:
            raise PackageIntegrityError(
                f"{name}: schema id {entry.get('schema_id')!r} is not a hub-canonical stream schema"
            )
        try:
            path = safe_join(base, name)
        except ValueError as exc:
            raise PackageIntegrityError(f"{name}: unsafe path in manifest") from exc
        if not path.is_file():
            raise PackageIntegrityError(f"{name}: listed in the manifest but missing")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
            raise PackageIntegrityError(f"{name}: SHA-256 does not match the manifest")
        rows: list[Mapping[str, Any]] = []
        for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PackageIntegrityError(f"{name}:{number}: invalid JSON") from exc
            if not isinstance(row, Mapping):
                raise PackageIntegrityError(f"{name}:{number}: row must be an object")
            rows.append(row)
        if len(rows) != entry.get("record_count"):
            raise PackageIntegrityError(
                f"{name}: {len(rows)} rows but the manifest states {entry.get('record_count')}"
            )
        if stream in streams:
            raise PackageIntegrityError(f"stream {stream!r} is listed twice")
        kept = tuple(row for row in rows if row.get("synthetic") is not True)
        dropped += len(rows) - len(kept)
        streams[stream] = kept
    return VerifiedPackage(
        producer=str(producer),
        contract_version=version,
        package_id=manifest.get("package_id"),
        mode=manifest.get("mode"),
        directory=str(base),
        streams=streams,
        files=tuple(dict(entry) for entry in files),
        synthetic_rows_dropped=dropped,
    )


class ContextClass(StrEnum):
    MONITORING_SITE = "MONITORING_SITE"  # a gauge, well or sampling location
    INFRASTRUCTURE_ASSET = "INFRASTRUCTURE_ASSET"  # a plant, reservoir, pumping station
    DOCUMENTARY = "DOCUMENTARY"  # a contract, award, project, property
    OTHER = "OTHER"


class CoordinateBasis(StrEnum):
    PRODUCER_POINT = "PRODUCER_POINT"  # producer-published lat/lon
    VERIFIED_SOURCE_COORDINATE = "VERIFIED_SOURCE_COORDINATE"
    MUNICIPALITY_LABEL_ONLY = "MUNICIPALITY_LABEL_ONLY"  # a name; never a point
    NONE = "NONE"


@dataclass(frozen=True)
class ContextRecord:
    """A foreign record, referenced verbatim.  Context, never evidence of a feature."""

    producer: str
    foreign_id: str
    record_kind: str
    name: str | None
    context_class: ContextClass
    coordinate_basis: CoordinateBasis
    lon_lat: tuple[float, float] | None
    municipality: str | None
    evidence_tier_raw: str | None
    review_status_raw: str | None
    producer_status_raw: str | None
    confidence_raw: float | None
    source_id_raw: str | None
    diagnostic_only: bool
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def placeable(self) -> bool:
        return self.lon_lat is not None


_AGUAYLUZ_MONITORING = frozenset(
    {
        "groundwater_well",
        "stream_gage",
        "tide_gauge",
        "water_quality_monitoring_location",
    }
)
_AGUAYLUZ_ASSETS = frozenset({"wastewater_treatment", "reservoir", "pumping_station"})
_MONEYSWEEP_DOCUMENTARY = frozenset({"project", "property", "contract"})
_VERIFIED_COORDINATE_STATE = "VERIFIED_SOURCE_COORDINATE"


def _point(location: Any) -> tuple[float, float] | None:
    if not isinstance(location, Mapping):
        return None
    lat = location.get("lat", location.get("latitude"))
    lon = location.get("lon", location.get("longitude"))
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        return validate_lon_lat(lon, lat)
    except ValueError:
        return None


def _municipality(location: Any) -> str | None:
    if isinstance(location, Mapping) and isinstance(location.get("municipality"), str):
        return location["municipality"].strip() or None
    return None


def aguayluz_context(package: VerifiedPackage) -> list[ContextRecord]:
    """Hydrologic monitoring sites and water assets from an aguayluz-pr package."""

    if package.producer != "aguayluz-pr":
        raise PackageIntegrityError("not an aguayluz-pr package")
    records: list[ContextRecord] = []
    for row in package.rows("entities"):
        if row.get("entity_type") != "utility_asset":
            continue
        attributes = (
            row.get("attributes") if isinstance(row.get("attributes"), Mapping) else {}
        )
        subtype = attributes.get("asset_subtype")
        if subtype in _AGUAYLUZ_MONITORING:
            context_class = ContextClass.MONITORING_SITE
        elif subtype in _AGUAYLUZ_ASSETS:
            context_class = ContextClass.INFRASTRUCTURE_ASSET
        else:
            continue
        point = _point(row.get("location"))
        records.append(
            ContextRecord(
                producer=package.producer,
                foreign_id=str(row["entity_id"]),
                record_kind=str(subtype),
                name=row.get("name"),
                context_class=context_class,
                coordinate_basis=(
                    CoordinateBasis.PRODUCER_POINT if point else CoordinateBasis.NONE
                ),
                lon_lat=point,
                municipality=_municipality(row.get("location")),
                evidence_tier_raw=attributes.get("evidence_tier"),
                review_status_raw=attributes.get("review_status"),
                producer_status_raw=attributes.get("status"),
                confidence_raw=row.get("confidence"),
                source_id_raw=row.get("source_id"),
                diagnostic_only=False,
                attributes=dict(attributes),
            )
        )
    records.sort(key=lambda r: r.foreign_id)
    return records


def moneysweep_context(package: VerifiedPackage) -> list[ContextRecord]:
    """Projects, properties and contracts from a moneysweep-pr package.

    All of it is documentary and diagnostic.  A coordinate is accepted only
    when the producer itself marks it as a verified source coordinate; a
    municipality name stays a name.
    """

    if package.producer != "moneysweep-pr":
        raise PackageIntegrityError("not a moneysweep-pr package")
    records: list[ContextRecord] = []
    for row in package.rows("entities"):
        kind = row.get("entity_type")
        if kind not in _MONEYSWEEP_DOCUMENTARY:
            continue
        attributes = (
            row.get("attributes") if isinstance(row.get("attributes"), Mapping) else {}
        )
        point = None
        basis = CoordinateBasis.NONE
        if (
            attributes.get("grid_v2_coordinate_evidence_state")
            == _VERIFIED_COORDINATE_STATE
        ):
            point = _point(row.get("location"))
            if point is not None:
                basis = CoordinateBasis.VERIFIED_SOURCE_COORDINATE
        municipality = _municipality(row.get("location"))
        if point is None and municipality is not None:
            basis = CoordinateBasis.MUNICIPALITY_LABEL_ONLY
        records.append(
            ContextRecord(
                producer=package.producer,
                foreign_id=str(row["entity_id"]),
                record_kind=str(kind),
                name=row.get("name"),
                context_class=ContextClass.DOCUMENTARY,
                coordinate_basis=basis,
                lon_lat=point,
                municipality=municipality,
                evidence_tier_raw=attributes.get("evidence_tier"),
                review_status_raw=attributes.get("review_status"),
                # Contractual or financial status, kept verbatim.  It is never
                # read as a physical state.
                producer_status_raw=attributes.get("status"),
                confidence_raw=row.get("confidence"),
                source_id_raw=row.get("source_id"),
                diagnostic_only=True,
                attributes=dict(attributes),
            )
        )
    records.sort(key=lambda r: r.foreign_id)
    return records


class EngineeredLifecycle(StrEnum):
    """Where an engineered asset stands.  Documents and observation differ."""

    PLANNED = "PLANNED"
    CONTRACTED = "CONTRACTED"
    FUNDED = "FUNDED"
    BUILT = "BUILT"
    OPERATIONAL = "OPERATIONAL"
    ABANDONED = "ABANDONED"
    UNKNOWN = "UNKNOWN"


DOCUMENTARY_LIFECYCLE: frozenset[EngineeredLifecycle] = frozenset(
    {
        EngineeredLifecycle.PLANNED,
        EngineeredLifecycle.CONTRACTED,
        EngineeredLifecycle.FUNDED,
        EngineeredLifecycle.UNKNOWN,
    }
)
PHYSICAL_LIFECYCLE: frozenset[EngineeredLifecycle] = frozenset(
    {
        EngineeredLifecycle.BUILT,
        EngineeredLifecycle.OPERATIONAL,
        EngineeredLifecycle.ABANDONED,
    }
)


def lifecycle_from_documents(record_kinds: Iterable[str]) -> EngineeredLifecycle:
    """The furthest lifecycle state documents alone can show.

    A contract shows something was contracted; an award or disbursement shows
    money moved.  Neither shows that anything was built, however the contract
    is labelled -- "completed" describes the contract term.
    """

    kinds = {str(kind).strip().lower() for kind in record_kinds}
    if kinds & {"funding_award", "transaction", "funded_by", "disbursement"}:
        return EngineeredLifecycle.FUNDED
    if kinds & {"contract", "receives_contract"}:
        return EngineeredLifecycle.CONTRACTED
    if kinds & {"project", "plan", "permit_application"}:
        return EngineeredLifecycle.PLANNED
    return EngineeredLifecycle.UNKNOWN


def lifecycle_from_observation(
    asserted: EngineeredLifecycle, sources: Sequence[SourceManifestation]
) -> EngineeredLifecycle:
    """Accept a physical lifecycle state only with a direct observation behind it."""

    if asserted in DOCUMENTARY_LIFECYCLE:
        return asserted
    if any(source.is_direct_measurement for source in sources):
        return asserted
    return EngineeredLifecycle.UNKNOWN


def context_assertion(record: ContextRecord, statement: str) -> EvidenceAssertion:
    """Attach a documentary record to a feature as a FUNCTION hypothesis.

    The assertion is created at ``CANDIDATE`` on a discovery-only basis, so the
    evidence rules cap it there whatever else is on the feature.  There is no
    way to produce an EXISTENCE, PHYSICAL_OPENING, ACCESSIBILITY or
    CONNECTIVITY assertion from context.
    """

    basis = (
        "funding_record"
        if record.record_kind in {"funding_award", "transaction"}
        else "contract_record"
    )
    return EvidenceAssertion(
        dimension=EvidenceDimension.FUNCTION,
        tier=EvidenceTier.CANDIDATE,
        claim_class=ClaimClass.HYPOTHESIS,
        basis=(basis,),
        statement=f"{statement} [context: {record.producer} {record.foreign_id}]",
    )


def nearby_context(
    feature: TypedRef,
    feature_lon_lat: tuple[float, float],
    records: Sequence[ContextRecord],
    *,
    threshold_m: float,
) -> list[tuple[ContextRecord, SpatialRelation]]:
    """Placeable context within a distance, as ``CANDIDATE_NOT_IDENTITY`` relations.

    Uses the existing federation ``within_distance`` relation.  Records that
    have no producer-published point are skipped: a municipality name is never
    turned into a location.
    """

    source = {
        "feature_id": str(feature),
        "geometry": {"type": "Point", "coordinates": list(feature_lon_lat)},
    }
    out: list[tuple[ContextRecord, SpatialRelation]] = []
    for record in records:
        if record.lon_lat is None:
            continue
        target = {
            "feature_id": f"{record.producer}:{record.foreign_id}",
            "geometry": {"type": "Point", "coordinates": list(record.lon_lat)},
        }
        relation = within_distance(source, target, threshold_m)
        if relation is not None:
            out.append((record, relation))
    out.sort(key=lambda pair: (pair[1].distance_m or 0.0, pair[0].foreign_id))
    return out
