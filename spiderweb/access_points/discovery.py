"""Bounded, metadata-only discovery runs over declared search areas.

:mod:`.acquisition` answers one question for one box.  This module turns that
into a run that can be planned, executed, written down and checked again:

* **targets** -- the boxes to ask about.  A target is either an analyst-drawn
  *corridor* (``configs/access_point_discovery_corridors.yaml``) or a box
  computed around a point a registry already holds.  A target is a search
  area.  It never becomes the geometry of a feature, and a corridor drawn from
  a locality name is recorded as an assumption;
* **plan** -- the first request every provider would make for every target,
  produced without touching the network;
* **run** -- the same thing executed under an explicit grant, with one request
  ceiling per target and one for the whole run;
* **catalogue** -- one sealed document listing every source the run saw, which
  targets listed it, and what the inventory published about it.  The registry
  builder reads this document; it never talks to a catalogue itself;
* **replay** -- the run rebuilt from the exact response bytes it kept, so the
  committed receipts can be reproduced and compared with a later run.

What a run establishes: that a catalogue *lists* a survey for a box on a date.
What it does not establish: that the survey covers any particular place inside
the box, what it measured there, or anything about a feature.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from federation.spatial_core import canonical_json_sha256
from pipeline.marine_reference_run import GeometryRole, ReferenceAOI
from pipeline.marine_sources import (
    BoundingBox,
    FrozenHttpResponse,
    Transport,
    freeze_http_response,
)

from . import CONTRACT_VERSION
from .acquisition import (
    PROVIDERS,
    Authorization,
    AuthorizationLevel,
    DiscoveredRow,
    DiscoveryReceipt,
    RequestBudgetExceeded,
    RunState,
    discover_sources,
    providers_for,
    replay_transport,
    to_source_manifestation,
)
from .monitoring import compare_receipts, review_flags, row_sha256
from .namespaces import REGISTRY_NAMESPACES, Namespace
from .registry import AccessPointRegistry
from .vertical import is_placeholder

DISCOVERY_VERSION = "access-point-source-discovery-run/1.0"
CORRIDORS_VERSION = "access_point_discovery_corridors_v1"
CORRIDORS_PATH = "configs/access_point_discovery_corridors.yaml"
DISCOVERY_DIR = "evidence/access_points/source_discovery"
POINTER_NAME = "CURRENT.json"
CATALOGUE_NAME = "source_catalogue.json"
CATALOGUE_SCHEMA = "access_point_source_catalogue/1.0"
POINTER_SCHEMA = "access_point_source_discovery_pointer/1.0"
RAW_DIR = "raw"

# A corridor file may say where to look.  It may not say where something is.
_FORBIDDEN_CORRIDOR_KEYS = frozenset(
    {
        "coordinates",
        "geometry",
        "point",
        "lon",
        "lat",
        "longitude",
        "latitude",
        "depth",
        "depth_m",
        "elevation",
        "elevation_m",
        "feature_id",
    }
)
_CORRIDOR_KEYS = frozenset(
    {"corridor_id", "registry", "locality", "seed_label", "bbox", "provenance"}
)


class DiscoveryConfigError(ValueError):
    """The corridor file is malformed or states something it may not state."""


class DiscoveryEvidenceError(ValueError):
    """Committed discovery evidence does not match its own hashes."""


class TargetBasis(StrEnum):
    ANALYST_CORRIDOR = "ANALYST_CORRIDOR"  # drawn from a locality name: an assumption
    REGISTERED_POINT_BUFFER = (
        "REGISTERED_POINT_BUFFER"  # computed from a registered point
    )


@dataclass(frozen=True, slots=True)
class DiscoveryTarget:
    """One search box.  Never a feature geometry."""

    target_id: str
    namespace: Namespace
    bbox: BoundingBox
    basis: TargetBasis
    provenance: str
    locality: str | None = None
    seed_label: str | None = None
    feature_id: str | None = None

    def __post_init__(self) -> None:
        if self.namespace not in REGISTRY_NAMESPACES:
            raise DiscoveryConfigError(
                f"{self.target_id}: {self.namespace.value} is not a registry"
            )
        # Reuses the repository's own rule: a discovery corridor cannot be
        # certified, so it can never stand in for a registered footprint.
        ReferenceAOI(
            aoi_id=self.target_id,
            bbox=self.bbox,
            role=GeometryRole.DISCOVERY_CORRIDOR,
            provenance=self.provenance,
            certified=False,
        )
        if self.basis is TargetBasis.REGISTERED_POINT_BUFFER and not self.feature_id:
            raise DiscoveryConfigError(
                f"{self.target_id}: a point buffer must name its feature"
            )
        if self.basis is TargetBasis.ANALYST_CORRIDOR and self.feature_id:
            raise DiscoveryConfigError(
                f"{self.target_id}: an analyst corridor must not be tied to a feature"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "namespace": self.namespace.value,
            "bbox": [
                self.bbox.min_lon,
                self.bbox.min_lat,
                self.bbox.max_lon,
                self.bbox.max_lat,
            ],
            "basis": self.basis.value,
            "role": GeometryRole.DISCOVERY_CORRIDOR.value,
            "certified": False,
            "provenance": self.provenance,
            "locality": self.locality,
            "seed_label": self.seed_label,
            "feature_id": self.feature_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DiscoveryTarget":
        return cls(
            target_id=str(data["target_id"]),
            namespace=Namespace(data["namespace"]),
            bbox=BoundingBox(*[float(v) for v in data["bbox"]]),
            basis=TargetBasis(data["basis"]),
            provenance=str(data["provenance"]),
            locality=data.get("locality"),
            seed_label=data.get("seed_label"),
            feature_id=data.get("feature_id"),
        )


# -- targets ---------------------------------------------------------------


def load_corridor_config(path: str | Path) -> Mapping[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise DiscoveryConfigError(f"{path} must contain a mapping")
    if data.get("version") != CORRIDORS_VERSION:
        raise DiscoveryConfigError(
            f"{path}: unsupported corridor file version {data.get('version')!r}"
        )
    half = data.get("point_buffer_half_width_deg")
    if not isinstance(half, (int, float)) or not 0 < float(half) <= 0.25:
        raise DiscoveryConfigError(
            "point_buffer_half_width_deg must be a number in (0, 0.25]"
        )
    if not isinstance(data.get("corridors"), list):
        raise DiscoveryConfigError("corridors must be a list")
    return data


def corridor_targets(config: Mapping[str, Any]) -> list[DiscoveryTarget]:
    """Analyst corridors from the config file, in file order."""

    targets: list[DiscoveryTarget] = []
    seen: set[str] = set()
    for entry in config["corridors"]:
        if not isinstance(entry, Mapping):
            raise DiscoveryConfigError("each corridor must be a mapping")
        keys = {str(k) for k in entry}
        stated = sorted(keys & _FORBIDDEN_CORRIDOR_KEYS)
        if stated:
            raise DiscoveryConfigError(
                f"corridor {entry.get('corridor_id')!r} states {stated}; a corridor is a "
                "search area and may not carry a position, a depth or a feature"
            )
        unknown = sorted(keys - _CORRIDOR_KEYS)
        if unknown:
            raise DiscoveryConfigError(
                f"corridor {entry.get('corridor_id')!r} has unknown keys {unknown}"
            )
        corridor_id = str(entry.get("corridor_id") or "").strip()
        if not corridor_id or corridor_id in seen:
            raise DiscoveryConfigError(
                f"corridor id missing or repeated: {corridor_id!r}"
            )
        seen.add(corridor_id)
        bbox = entry.get("bbox")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(v, (int, float)) for v in bbox)
        ):
            raise DiscoveryConfigError(f"{corridor_id}: bbox must be four numbers")
        provenance = " ".join(str(entry.get("provenance") or "").split())
        if not provenance:
            raise DiscoveryConfigError(f"{corridor_id}: provenance is required")
        try:
            namespace = Namespace(entry.get("registry"))
        except ValueError as exc:
            raise DiscoveryConfigError(f"{corridor_id}: unknown registry") from exc
        try:
            box = BoundingBox(*[float(v) for v in bbox])
        except ValueError as exc:
            raise DiscoveryConfigError(f"{corridor_id}: {exc}") from exc
        targets.append(
            DiscoveryTarget(
                target_id=corridor_id,
                namespace=namespace,
                bbox=box,
                basis=TargetBasis.ANALYST_CORRIDOR,
                provenance=provenance,
                locality=(str(entry["locality"]) if entry.get("locality") else None),
                seed_label=(
                    str(entry["seed_label"]) if entry.get("seed_label") else None
                ),
            )
        )
    return targets


def registered_points(registry: AccessPointRegistry) -> dict[str, tuple[float, float]]:
    """Features whose observation states a point.  Nothing is inferred."""

    points: dict[str, tuple[float, float]] = {}
    for feature_id in sorted(registry.features):
        feature = registry.features[feature_id]
        for oid in feature.observation_ids:
            geometry = registry.observations[oid].geometry
            if geometry and geometry.get("type") == "Point":
                lon, lat = geometry["coordinates"][:2]
                points[feature_id] = (float(lon), float(lat))
                break
    return points


def point_targets(
    registry: AccessPointRegistry, *, half_width_deg: float
) -> list[DiscoveryTarget]:
    """A search box around every point a registry already holds."""

    if not 0 < half_width_deg <= 0.25:
        raise DiscoveryConfigError("half_width_deg must be in (0, 0.25]")
    targets: list[DiscoveryTarget] = []
    for feature_id, (lon, lat) in registered_points(registry).items():
        targets.append(
            DiscoveryTarget(
                target_id="point_buffer_" + feature_id.lower().replace("-", "_"),
                namespace=registry.namespace,
                bbox=BoundingBox(
                    round(lon - half_width_deg, 6),
                    round(lat - half_width_deg, 6),
                    round(lon + half_width_deg, 6),
                    round(lat + half_width_deg, 6),
                ),
                basis=TargetBasis.REGISTERED_POINT_BUFFER,
                provenance=(
                    f"Box of half-width {half_width_deg} degrees computed around the "
                    f"point registered for {feature_id}; a search area, not an extent."
                ),
                feature_id=feature_id,
            )
        )
    return targets


def build_targets(
    config: Mapping[str, Any], registries: Sequence[AccessPointRegistry]
) -> list[DiscoveryTarget]:
    targets = corridor_targets(config)
    for registry in registries:
        targets.extend(
            point_targets(
                registry, half_width_deg=float(config["point_buffer_half_width_deg"])
            )
        )
    ids = [t.target_id for t in targets]
    if len(ids) != len(set(ids)):
        raise DiscoveryConfigError("target ids are not unique")
    return targets


# -- plan ------------------------------------------------------------------


class _PlanOnly(Exception):
    """Raised by the planning transport so no provider gets past its first URL."""


def _first_request_url(provider_id: str, bbox: BoundingBox) -> str:
    seen: list[str] = []

    def capture(url: str) -> FrozenHttpResponse:
        seen.append(url)
        raise _PlanOnly

    try:
        PROVIDERS[provider_id].discover(bbox, capture)
    except _PlanOnly:
        pass
    if len(seen) != 1:
        raise RuntimeError(f"{provider_id} did not issue exactly one first request")
    return seen[0]


def plan(targets: Sequence[DiscoveryTarget]) -> dict[str, Any]:
    """What a run would ask, computed without any network access."""

    entries = []
    for target in targets:
        entries.append(
            {
                **target.to_dict(),
                "providers": [
                    {
                        "provider_id": spec.provider_id,
                        "family": spec.family.value,
                        "first_request_url": _first_request_url(
                            spec.provider_id, target.bbox
                        ),
                    }
                    for spec in providers_for(target.namespace)
                ],
            }
        )
    first_requests = sum(len(e["providers"]) for e in entries)
    return {
        "schema": "access_point_source_discovery_plan/1.0",
        "discovery_version": DISCOVERY_VERSION,
        "targets": entries,
        "first_requests": first_requests,
        "note": (
            "one request per provider per target at minimum; a catalogue that pages "
            "adds requests, bounded by the grant"
        ),
        "network_used": False,
    }


# -- run -------------------------------------------------------------------


@dataclass(frozen=True)
class TargetResult:
    target: DiscoveryTarget
    receipt: DiscoveryReceipt


@dataclass(frozen=True)
class DiscoveryRun:
    run_id: str
    discovered_utc: str
    authorization: Authorization
    max_total_requests: int
    results: tuple[TargetResult, ...]

    @property
    def total_requests(self) -> int:
        return sum(
            run.request_count for result in self.results for run in result.receipt.runs
        )

    @property
    def total_bytes(self) -> int:
        return sum(
            response.response_size
            for result in self.results
            for run in result.receipt.runs
            for response in run.responses
        )

    @property
    def state(self) -> RunState:
        states = {result.receipt.state for result in self.results}
        if not states:
            return RunState.NOT_RUN
        for worst in (RunState.FAIL, RunState.NOT_AUTHORIZED, RunState.NOT_RUN):
            if worst in states:
                return worst
        return RunState.PASS if RunState.PASS in states else RunState.ZERO


def _capped(transport: Transport, limit: int) -> Transport:
    used = 0

    def call(url: str) -> FrozenHttpResponse:
        nonlocal used
        if used >= limit:
            raise RequestBudgetExceeded(
                f"run-wide request ceiling of {limit} is exhausted"
            )
        used += 1
        return transport(url)

    return call


def run_discovery(
    targets: Sequence[DiscoveryTarget],
    *,
    run_id: str,
    discovered_utc: str,
    transport: Transport,
    authorization: Authorization,
    max_total_requests: int,
) -> DiscoveryRun:
    """Ask every provider about every target, inside two request ceilings.

    ``authorization.max_requests`` bounds one target; ``max_total_requests``
    bounds the run.  Without a metadata grant every provider is reported
    ``NOT_AUTHORIZED`` and nothing is requested.
    """

    if not run_id.strip() or "/" in run_id or run_id.startswith("."):
        raise ValueError("run_id must be a plain directory name")
    if max_total_requests < 1:
        raise ValueError("max_total_requests must be at least 1")
    ids = [t.target_id for t in targets]
    if len(ids) != len(set(ids)):
        raise DiscoveryConfigError("target ids are not unique")
    shared = _capped(transport, max_total_requests)
    results = [
        TargetResult(
            target,
            discover_sources(
                target.namespace,
                target.bbox,
                discovered_utc=discovered_utc,
                transport=shared,
                authorization=authorization,
            ),
        )
        for target in targets
    ]
    return DiscoveryRun(
        run_id, discovered_utc, authorization, max_total_requests, tuple(results)
    )


# -- catalogue -------------------------------------------------------------


def _envelope(row: DiscoveredRow) -> list[float] | None:
    box = row.envelope
    if box is None:
        return None
    return [box.min_lon, box.min_lat, box.max_lon, box.max_lat]


def _review_flags(
    run: DiscoveryRun, feature_points: Mapping[Namespace, Mapping[str, tuple]]
) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for result in run.results:
        points = feature_points.get(result.target.namespace, {})
        if not points:
            continue
        comparisons = compare_receipts(None, result.receipt)
        for flag in review_flags(comparisons, points):
            key = (flag.feature_id, flag.provider_id, flag.native_identifier)
            seen.setdefault(
                key,
                {
                    "feature_id": flag.feature_id,
                    "provider_id": flag.provider_id,
                    "native_identifier": flag.native_identifier,
                    "change": flag.change.value,
                    "envelope_relation": flag.envelope_relation,
                    "basis": "POINT_IN_ENVELOPE_PLANNING",
                },
            )
    return [seen[key] for key in sorted(seen)]


def build_catalogue(
    run: DiscoveryRun,
    *,
    feature_points: Mapping[Namespace, Mapping[str, tuple]] | None = None,
) -> dict[str, Any]:
    """Every source the run saw, once, with the targets that listed it."""

    sources: dict[tuple[str, str], dict[str, Any]] = {}
    inconsistent: list[dict[str, str]] = []
    targets = []
    for result in run.results:
        target, receipt = result.target, result.receipt
        document = receipt.to_document()
        targets.append(
            {
                **target.to_dict(),
                "state": receipt.state.value,
                "zero_result_claim_permitted": receipt.zero_result_claim_permitted,
                "receipt_file": f"{target.target_id}.receipt.json",
                "receipt_content_sha256": document["content_sha256"],
                "providers": [
                    {
                        "provider_id": r.provider_id,
                        "state": r.state.value,
                        "row_count": r.row_count,
                        "request_count": r.request_count,
                        "response_bytes": sum(x.response_size for x in r.responses),
                        "error": r.error,
                    }
                    for r in receipt.runs
                ],
            }
        )
        for provider_run in receipt.runs:
            spec = PROVIDERS[provider_run.provider_id]
            for row in provider_run.rows:
                key = (spec.provider_id, row.native_identifier)
                digest = row_sha256(row)
                entry = sources.get(key)
                if entry is None:
                    datum = row.vertical_datum_raw
                    entry = sources[key] = {
                        "source_id": to_source_manifestation(spec, row).source_id,
                        "provider_id": spec.provider_id,
                        "family": spec.family.value,
                        "native_identifier": row.native_identifier,
                        "identifier_is_stable": row.identifier_is_stable,
                        "title": row.title,
                        "metadata_uri": row.metadata_uri,
                        "data_access_uri": row.data_access_uri,
                        "surveyed": row.surveyed,
                        "published": row.published,
                        "vertical_datum_raw": datum,
                        "vertical_datum_is_placeholder": (
                            None if datum is None else is_placeholder(datum)
                        ),
                        "horizontal_datum_raw": row.horizontal_datum_raw,
                        "envelope": _envelope(row),
                        "row_sha256": digest,
                        "namespaces": set(),
                        "targets": set(),
                    }
                elif entry["row_sha256"] != digest:
                    inconsistent.append(
                        {
                            "provider_id": spec.provider_id,
                            "native_identifier": row.native_identifier,
                            "target_id": target.target_id,
                        }
                    )
                entry["namespaces"].add(target.namespace.value)
                entry["targets"].add(target.target_id)

    rows = []
    for key in sorted(sources):
        entry = dict(sources[key])
        entry["namespaces"] = sorted(entry["namespaces"])
        entry["targets"] = sorted(entry["targets"])
        rows.append(entry)

    by_provider: dict[str, int] = {}
    by_namespace: dict[str, int] = {}
    for entry in rows:
        by_provider[entry["provider_id"]] = by_provider.get(entry["provider_id"], 0) + 1
        for namespace in entry["namespaces"]:
            by_namespace[namespace] = by_namespace.get(namespace, 0) + 1
    with_datum = [e for e in rows if e["vertical_datum_raw"] is not None]
    provider_states: dict[str, int] = {}
    for result in run.results:
        for provider_run in result.receipt.runs:
            provider_states[provider_run.state.value] = (
                provider_states.get(provider_run.state.value, 0) + 1
            )

    body: dict[str, Any] = {
        "schema": CATALOGUE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "discovery_version": DISCOVERY_VERSION,
        "run_id": run.run_id,
        "discovered_utc": run.discovered_utc,
        "authorization": {
            "level": run.authorization.level.value,
            "granted_by": run.authorization.granted_by,
            "max_requests_per_target": run.authorization.max_requests,
            "max_total_requests": run.max_total_requests,
        },
        "state": run.state.value,
        "targets": targets,
        "sources": rows,
        "totals": {
            "targets": len(targets),
            "provider_runs": sum(provider_states.values()),
            "provider_runs_by_state": dict(sorted(provider_states.items())),
            "requests": run.total_requests,
            "response_bytes": run.total_bytes,
            "sources": len(rows),
            "sources_by_provider": dict(sorted(by_provider.items())),
            "sources_by_namespace": dict(sorted(by_namespace.items())),
            "sources_with_stable_identifier": sum(
                1 for e in rows if e["identifier_is_stable"]
            ),
            "sources_stating_a_vertical_datum_field": len(with_datum),
            "vertical_datum_placeholders": sum(
                1 for e in with_datum if e["vertical_datum_is_placeholder"]
            ),
            "sources_with_data_access_uri": sum(
                1 for e in rows if e["data_access_uri"]
            ),
            "inconsistent_rows_within_run": len(inconsistent),
        },
        "inconsistent_rows": inconsistent,
        "review_flags": _review_flags(run, feature_points or {}),
        "automatic_promotions": 0,
        "data_products_downloaded": 0,
        "invariants": [
            "a target is a search area; it is never the geometry of a feature",
            "an analyst corridor is drawn from a locality name and is an assumption",
            "being listed for a box does not show that a survey covers a place in it",
            "inventory coverage is not a depth or elevation measurement",
            "a failed provider says nothing about coverage",
            "a review flag never changes a feature's status",
            "no data product was downloaded by this run",
        ],
    }
    body["content_sha256"] = canonical_json_sha256(body)
    return body


def verify_sealed(document: Mapping[str, Any], *, what: str) -> None:
    body = dict(document)
    stated = body.pop("content_sha256", None)
    if not stated or canonical_json_sha256(body) != stated:
        raise DiscoveryEvidenceError(f"{what} does not match its content hash")


def load_catalogue(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != CATALOGUE_SCHEMA:
        raise DiscoveryEvidenceError(f"{path} is not a source catalogue")
    verify_sealed(document, what=str(path))
    return document


def catalogue_rows(
    catalogue: Mapping[str, Any],
) -> list[tuple[str, list[Namespace], DiscoveredRow]]:
    """Catalogue entries as (provider, registries that listed it, row)."""

    out = []
    for entry in catalogue["sources"]:
        envelope = entry.get("envelope")
        out.append(
            (
                str(entry["provider_id"]),
                [Namespace(n) for n in entry["namespaces"]],
                DiscoveredRow(
                    native_identifier=str(entry["native_identifier"]),
                    identifier_is_stable=bool(entry["identifier_is_stable"]),
                    title=str(entry["title"]),
                    attributes={},
                    envelope=None if envelope is None else BoundingBox(*envelope),
                    metadata_uri=entry.get("metadata_uri"),
                    data_access_uri=entry.get("data_access_uri"),
                    surveyed=entry.get("surveyed"),
                    published=entry.get("published"),
                    vertical_datum_raw=entry.get("vertical_datum_raw"),
                    horizontal_datum_raw=entry.get("horizontal_datum_raw"),
                ),
            )
        )
    return out


# -- persistence -----------------------------------------------------------


def _write_json(path: Path, document: Mapping[str, Any]) -> str:
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_run(
    run: DiscoveryRun,
    discovery_root: str | Path,
    *,
    feature_points: Mapping[Namespace, Mapping[str, tuple]] | None = None,
    keep_raw: bool = True,
    set_current: bool = True,
) -> dict[str, Any]:
    """Write receipts, the catalogue and (optionally) the exact response bytes.

    Refuses to write over an existing run directory: a run is a record of what
    was seen on a date and is never edited afterwards.
    """

    root = Path(discovery_root)
    run_dir = root / run.run_id
    if run_dir.exists():
        raise FileExistsError(f"{run_dir} already exists; a run is never overwritten")
    run_dir.mkdir(parents=True)
    for result in run.results:
        _write_json(
            run_dir / f"{result.target.target_id}.receipt.json",
            result.receipt.to_document(),
        )
        if keep_raw:
            raw = run_dir / RAW_DIR / result.target.target_id
            for provider_run in result.receipt.runs:
                for index, response in enumerate(provider_run.responses):
                    freeze_http_response(
                        response, raw, stem=f"{provider_run.provider_id}_{index:02d}"
                    )
    catalogue = build_catalogue(run, feature_points=feature_points)
    catalogue_sha = _write_json(run_dir / CATALOGUE_NAME, catalogue)
    if set_current:
        _write_json(
            root / POINTER_NAME,
            {
                "schema": POINTER_SCHEMA,
                "run_id": run.run_id,
                "catalogue": f"{run.run_id}/{CATALOGUE_NAME}",
                "catalogue_sha256": catalogue_sha,
                "raw_bytes_kept": keep_raw,
            },
        )
    return catalogue


def current_catalogue_path(discovery_root: str | Path) -> Path | None:
    """The catalogue the pointer names, hash-checked; ``None`` if there is no run."""

    root = Path(discovery_root)
    pointer_path = root / POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer.get("schema") != POINTER_SCHEMA:
        raise DiscoveryEvidenceError(f"{pointer_path} is not a discovery pointer")
    relative = Path(str(pointer["catalogue"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise DiscoveryEvidenceError("pointer must name a path inside the run folder")
    path = root / relative
    if not path.is_file():
        raise DiscoveryEvidenceError(f"pointer names a missing catalogue: {relative}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer["catalogue_sha256"]:
        raise DiscoveryEvidenceError(f"{relative} does not match the pointer's hash")
    return path


def replay_run(run_dir: str | Path) -> DiscoveryRun:
    """Rebuild a run from the exact bytes it kept.  No network is used.

    The original grant is carried over as a historical fact so the rebuilt
    receipts are byte-identical to the committed ones.
    """

    directory = Path(run_dir)
    catalogue = load_catalogue(directory / CATALOGUE_NAME)
    grant = catalogue["authorization"]
    authorization = Authorization(
        AuthorizationLevel(grant["level"]),
        str(grant["granted_by"]),
        int(grant["max_requests_per_target"]),
    )
    results = []
    for entry in catalogue["targets"]:
        target = DiscoveryTarget.from_dict(entry)
        raw = directory / RAW_DIR / target.target_id
        if not raw.is_dir():
            raise DiscoveryEvidenceError(f"no kept bytes for target {target.target_id}")
        results.append(
            TargetResult(
                target,
                discover_sources(
                    target.namespace,
                    target.bbox,
                    discovered_utc=str(catalogue["discovered_utc"]),
                    transport=replay_transport(raw),
                    authorization=authorization,
                ),
            )
        )
    return DiscoveryRun(
        str(catalogue["run_id"]),
        str(catalogue["discovered_utc"]),
        authorization,
        int(grant["max_total_requests"]),
        tuple(results),
    )


def verify_run(run_dir: str | Path) -> list[str]:
    """Problems found when the kept bytes are replayed against the record."""

    directory = Path(run_dir)
    problems: list[str] = []
    try:
        catalogue = load_catalogue(directory / CATALOGUE_NAME)
        replayed = replay_run(directory)
    except (DiscoveryEvidenceError, ValueError, LookupError, OSError) as exc:
        return [f"{type(exc).__name__}: {exc}"]
    by_id = {entry["target_id"]: entry for entry in catalogue["targets"]}
    for result in replayed.results:
        target_id = result.target.target_id
        rebuilt = result.receipt.to_document()
        receipt_path = directory / f"{target_id}.receipt.json"
        if not receipt_path.is_file():
            problems.append(f"{target_id}: receipt file is missing")
            continue
        committed = json.loads(receipt_path.read_text(encoding="utf-8"))
        if committed != rebuilt:
            problems.append(f"{target_id}: replay does not reproduce the receipt")
        if rebuilt["content_sha256"] != by_id[target_id]["receipt_content_sha256"]:
            problems.append(f"{target_id}: receipt hash differs from the catalogue")
    rebuilt_catalogue = build_catalogue(replayed)
    for key in ("targets", "sources", "totals", "state", "inconsistent_rows"):
        if rebuilt_catalogue[key] != catalogue[key]:
            problems.append(f"catalogue field {key!r} is not reproduced by replay")
    return problems


def compare_with_listing(
    run: DiscoveryRun,
    *,
    target_id: str,
    bbox: Sequence[float],
    listed: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Compare one target with an earlier list of native identifiers.

    ``listed`` maps a provider id to the identifiers an earlier record named
    for the *same box*.  A provider that did not run cleanly is reported as not
    comparable; its absence is never read as a withdrawal.
    """

    result = next((r for r in run.results if r.target.target_id == target_id), None)
    if result is None:
        raise KeyError(target_id)
    box = result.target.bbox
    if [box.min_lon, box.min_lat, box.max_lon, box.max_lat] != [float(v) for v in bbox]:
        raise ValueError("the earlier record covers a different box")
    out: dict[str, Any] = {"target_id": target_id, "providers": {}}
    runs = {r.provider_id: r for r in result.receipt.runs}
    for provider_id in sorted(listed):
        current = runs.get(provider_id)
        if current is None or current.state not in {RunState.PASS, RunState.ZERO}:
            out["providers"][provider_id] = {
                "comparable": False,
                "reason": "provider did not run cleanly in this run",
            }
            continue
        before = {str(v) for v in listed[provider_id]}
        now = {row.native_identifier for row in current.rows}
        out["providers"][provider_id] = {
            "comparable": True,
            "listed_before": len(before),
            "listed_now": len(now),
            "in_both": len(before & now),
            "only_before": sorted(before - now),
            "only_now": sorted(now - before),
        }
    return out
