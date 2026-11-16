"""Provider-aware source discovery shared by both registries.

This layer does not add a downloader.  It standardises on the transport that
already exists and is already tested offline --
``pipeline.marine_sources.Transport`` / ``FrozenHttpResponse`` /
``freeze_http_response`` -- and calls the existing, count-closing fetchers for
the NOAA catalogues and the US Interagency Elevation Inventory.  That inventory
lists terrestrial LiDAR as well as bathymetric surveys, so one discovery path
serves the inland and the off-shore registry.

What it adds
------------
* a default-deny authorisation gate: nothing touches the network unless the
  caller holds an explicit grant, and the only grant implemented here is
  metadata discovery.  There is no bulk-download path in this module;
* retry and rate-limit wrappers around the shared transport;
* an offline replay transport over frozen ``.bin`` + ``.manifest.json`` pairs;
* the adapter lifecycle as a declared vocabulary with allowed transitions;
* one receipt shape that keeps four dates apart: discovered, published,
  surveyed, retrieved.

Inventory coverage is not a measurement.  Every source produced here is
``REFERENCED_ONLY`` with unknown coverage, so it can be cited for provenance but
can never satisfy a direct-observation gate.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.request import Request, urlopen

from federation.spatial_core import canonical_json_sha256
from gebco.marine_evidence import CoverageState, ProductStage, SensorType
from pipeline.marine_lidar_sources import LidarInventoryLayer, fetch_all_usiei_pages
from pipeline.marine_reference_run import classify_bbox_relation, esri_feature_envelope
from pipeline.marine_sources import (
    BoundingBox,
    CatalogFamily,
    FrozenHttpResponse,
    Transport,
    fetch_all_ncei_catalog_pages,
    fetch_all_nos_bag_pages,
    freeze_http_response,
)

from . import CONTRACT_VERSION
from .models import SourceManifestation
from .namespaces import Namespace, source_id
from .vocabulary import ProvenanceState

ACQUISITION_VERSION = "access-point-acquisition/1.0"
AUTHORIZATION_ENV = "SPIDERWEB_ACCESS_POINT_ACQUISITION"


# -- lifecycle -------------------------------------------------------------


class LifecycleState(StrEnum):
    DISCOVER = "DISCOVER"
    INSPECT_METADATA = "INSPECT_METADATA"
    IDENTIFY_SOURCE = "IDENTIFY_SOURCE"
    VALIDATE_SCOPE = "VALIDATE_SCOPE"
    VERIFY_ACCESS = "VERIFY_ACCESS"
    PLAN_ACQUISITION = "PLAN_ACQUISITION"
    ACQUIRE_IF_AUTHORIZED = "ACQUIRE_IF_AUTHORIZED"
    FREEZE_RAW = "FREEZE_RAW"
    VERIFY_SCHEMA = "VERIFY_SCHEMA"
    VALIDATE_GEOMETRY = "VALIDATE_GEOMETRY"
    NORMALIZE = "NORMALIZE"
    INDEX = "INDEX"
    ANALYZE = "ANALYZE"
    PRESERVE_LINEAGE = "PRESERVE_LINEAGE"
    REGISTER_EVIDENCE = "REGISTER_EVIDENCE"
    VALIDATE_OUTPUT = "VALIDATE_OUTPUT"


LIFECYCLE_ORDER: tuple[LifecycleState, ...] = tuple(LifecycleState)


class StepOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class LifecycleError(RuntimeError):
    """A lifecycle step was attempted out of order or after a failure."""


@dataclass(frozen=True, slots=True)
class LifecycleStep:
    state: LifecycleState
    outcome: StepOutcome
    detail: str


class LifecycleLog:
    """Ordered record of what was done.  Steps cannot be skipped silently."""

    def __init__(self) -> None:
        self._steps: list[LifecycleStep] = []

    @property
    def steps(self) -> tuple[LifecycleStep, ...]:
        return tuple(self._steps)

    @property
    def halted(self) -> bool:
        return bool(self._steps) and self._steps[-1].outcome in {
            StepOutcome.FAIL,
            StepOutcome.BLOCKED,
            StepOutcome.NOT_AUTHORIZED,
        }

    def record(self, state: LifecycleState, outcome: StepOutcome, detail: str) -> None:
        expected = (
            LIFECYCLE_ORDER[len(self._steps)]
            if len(self._steps) < len(LIFECYCLE_ORDER)
            else None
        )
        if self.halted:
            raise LifecycleError(
                f"lifecycle halted at {self._steps[-1].state.value}; "
                f"{state.value} cannot run after it"
            )
        if state is not expected:
            raise LifecycleError(
                f"{state.value} attempted but the next step is "
                f"{expected.value if expected else 'none (lifecycle complete)'}"
            )
        self._steps.append(LifecycleStep(state, outcome, detail))

    def to_list(self) -> list[dict[str, str]]:
        return [
            {"state": s.state.value, "outcome": s.outcome.value, "detail": s.detail}
            for s in self._steps
        ]


# -- authorisation ---------------------------------------------------------


class AuthorizationLevel(StrEnum):
    NONE = "NONE"
    METADATA_DISCOVERY = "METADATA_DISCOVERY"


class AcquisitionNotAuthorized(PermissionError):
    """A network operation was attempted without an explicit grant."""


@dataclass(frozen=True, slots=True)
class Authorization:
    """An explicit, bounded grant.  The default grants nothing."""

    level: AuthorizationLevel = AuthorizationLevel.NONE
    granted_by: str = ""
    max_requests: int = 0

    def __post_init__(self) -> None:
        if self.level is not AuthorizationLevel.NONE:
            if not self.granted_by.strip():
                raise ValueError("a grant must name who authorised it")
            if self.max_requests < 1:
                raise ValueError("a grant must bound the number of requests")

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "Authorization":
        """``SPIDERWEB_ACCESS_POINT_ACQUISITION=metadata:<max_requests>:<granted_by>``.

        Anything else, including an unset variable, grants nothing.
        """

        raw = (environ if environ is not None else os.environ).get(
            AUTHORIZATION_ENV, ""
        )
        parts = raw.split(":", 2)
        if len(parts) != 3 or parts[0] != "metadata":
            return cls()
        try:
            limit = int(parts[1])
        except ValueError:
            return cls()
        if limit < 1 or not parts[2].strip():
            return cls()
        return cls(AuthorizationLevel.METADATA_DISCOVERY, parts[2].strip(), limit)

    def require(self, level: AuthorizationLevel) -> None:
        if self.level is not level:
            raise AcquisitionNotAuthorized(
                f"{level.value} is not authorised (grant is {self.level.value}); set "
                f"{AUTHORIZATION_ENV} or pass an explicit Authorization"
            )


# -- transport wrappers ----------------------------------------------------


def denied_transport(url: str) -> FrozenHttpResponse:
    raise AcquisitionNotAuthorized(f"network access is not authorised: {url}")


class RequestBudgetExceeded(RuntimeError):
    """The authorised number of requests was used up."""


def budgeted(transport: Transport, authorization: Authorization) -> Transport:
    """Enforce the grant: no grant, no request; grant spent, no request."""

    used = 0

    def call(url: str) -> FrozenHttpResponse:
        nonlocal used
        authorization.require(AuthorizationLevel.METADATA_DISCOVERY)
        if used >= authorization.max_requests:
            raise RequestBudgetExceeded(
                f"authorised request budget of {authorization.max_requests} is exhausted"
            )
        used += 1
        return transport(url)

    return call


def with_retry(
    transport: Transport,
    *,
    attempts: int = 3,
    backoff_s: float = 1.5,
    sleep: Callable[[float], None] = time.sleep,
    retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504}),
) -> Transport:
    """Retry transient failures.  The last response or error is always surfaced.

    A failure is never turned into an empty success: after the final attempt
    the caller sees the failing status or the original exception.
    """

    if attempts < 1 or backoff_s < 0:
        raise ValueError("attempts must be >= 1 and backoff_s >= 0")

    def call(url: str) -> FrozenHttpResponse:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = transport(url)
            except (AcquisitionNotAuthorized, RequestBudgetExceeded):
                raise
            except OSError as exc:
                last_error = exc
            else:
                if response.status not in retry_statuses or attempt == attempts:
                    return response
                last_error = None
            if attempt < attempts:
                sleep(backoff_s * attempt)
        assert last_error is not None
        raise last_error

    return call


def with_rate_limit(
    transport: Transport,
    *,
    min_interval_s: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Transport:
    if min_interval_s < 0:
        raise ValueError("min_interval_s must be non-negative")
    last: float | None = None

    def call(url: str) -> FrozenHttpResponse:
        nonlocal last
        now = clock()
        if last is not None and now - last < min_interval_s:
            sleep(min_interval_s - (now - last))
        last = clock()
        return transport(url)

    return call


class UnexpectedRedirect(RuntimeError):
    """A catalogue endpoint answered from a different URL than the one asked."""


# Response headers worth keeping as evidence.  Everything else -- cookies,
# load-balancer tokens, server banners -- is dropped before a response is
# frozen, so nothing session-specific is ever written next to the bytes.
RECORDED_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "content-encoding",
        "date",
        "etag",
        "last-modified",
    }
)
GENERIC_USER_AGENT = "metadata-discovery-client/1.0"


def live_transport(
    *, user_agent: str = GENERIC_USER_AGENT, timeout: float = 60.0
) -> Transport:
    """A real HTTPS transport for metadata discovery.

    It differs from ``pipeline.marine_sources.default_transport`` in three
    ways that matter for a run whose bytes are kept: the user agent is generic
    (no repository or operator name leaves the machine), only an allow-list of
    response headers is recorded, and a redirect is refused instead of being
    followed silently, so the recorded URL is always the URL that was asked
    and a frozen response can be replayed by it.

    Nothing here grants anything: wrap it in :func:`budgeted` before use.
    """

    if not user_agent.strip():
        raise ValueError("a user agent is required")

    def call(url: str) -> FrozenHttpResponse:
        if not url.startswith("https://"):
            raise ValueError(f"only https catalogue endpoints are allowed: {url}")
        request = Request(url, headers={"User-Agent": user_agent})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - https only
            body = response.read()
            status = int(response.status)
            headers = {
                str(k): str(v)
                for k, v in response.headers.items()
                if str(k).lower() in RECORDED_RESPONSE_HEADERS
            }
            final_url = response.geturl()
        if final_url != url:
            raise UnexpectedRedirect(f"{url} answered from {final_url}")
        return FrozenHttpResponse(
            request_url=url,
            status=status,
            retrieved_utc=datetime.now(timezone.utc).isoformat(),
            response_sha256=hashlib.sha256(body).hexdigest(),
            response_size=len(body),
            headers=headers,
            body=body,
        )

    return call


class Recorder:
    """Keeps every frozen response a run produced, in request order."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self.responses: list[FrozenHttpResponse] = []

    def __call__(self, url: str) -> FrozenHttpResponse:
        response = self._transport(url)
        self.responses.append(response)
        return response

    def freeze_all(self, directory: Path, *, stem_prefix: str) -> list[dict[str, Any]]:
        """Persist exact bytes with the existing freeze helper; return manifests."""

        manifests = []
        for index, response in enumerate(self.responses):
            body_path, manifest_path = freeze_http_response(
                response, directory, stem=f"{stem_prefix}_{index:04d}"
            )
            entry = dict(response.manifest())
            entry["body_file"] = body_path.name
            entry["manifest_file"] = manifest_path.name
            manifests.append(entry)
        return manifests


class ReplayMiss(LookupError):
    """An offline fixture set holds no response for the requested URL."""


def replay_transport(directory: Path) -> Transport:
    """Serve frozen ``<stem>.bin`` + ``<stem>.manifest.json`` pairs by URL.

    Bytes are re-hashed on load; a fixture that no longer matches its manifest
    is refused.  An unknown URL raises -- it is never answered with an empty
    success.
    """

    table: dict[str, FrozenHttpResponse] = {}
    for manifest_path in sorted(Path(directory).glob("*.manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        body_path = manifest_path.with_name(
            manifest_path.name.replace(".manifest.json", ".bin")
        )
        body = body_path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if (
            digest != manifest["response_sha256"]
            or len(body) != manifest["response_size"]
        ):
            raise ValueError(
                f"frozen fixture {body_path.name} does not match its manifest"
            )
        url = manifest["request_url"]
        if url in table:
            raise ValueError(f"duplicate frozen fixture for {url}")
        table[url] = FrozenHttpResponse(
            request_url=url,
            status=int(manifest["status"]),
            retrieved_utc=manifest["retrieved_utc"],
            response_sha256=digest,
            response_size=len(body),
            headers=dict(manifest.get("headers") or {}),
            body=body,
        )

    def call(url: str) -> FrozenHttpResponse:
        try:
            return table[url]
        except KeyError:
            raise ReplayMiss(url) from None

    return call


# -- providers -------------------------------------------------------------


class SourceFamily(StrEnum):
    TERRESTRIAL_LIDAR_INVENTORY = "TERRESTRIAL_LIDAR_INVENTORY"
    TOPOBATHYMETRIC_LIDAR_INVENTORY = "TOPOBATHYMETRIC_LIDAR_INVENTORY"
    BATHYMETRIC_LIDAR_INVENTORY = "BATHYMETRIC_LIDAR_INVENTORY"
    IFSAR_INVENTORY = "IFSAR_INVENTORY"
    OTHER_BATHYMETRIC_SURVEY_INVENTORY = "OTHER_BATHYMETRIC_SURVEY_INVENTORY"
    MULTIBEAM_SURVEY_CATALOG = "MULTIBEAM_SURVEY_CATALOG"
    SOUNDING_SURVEY_CATALOG = "SOUNDING_SURVEY_CATALOG"
    HYDROGRAPHIC_BAG_INVENTORY = "HYDROGRAPHIC_BAG_INVENTORY"


class Completeness(StrEnum):
    COUNT_CLOSED = "COUNT_CLOSED"  # rows retained == count reported
    TRANSFER_LIMIT_FOLLOWED = (
        "TRANSFER_LIMIT_FOLLOWED"  # paged until the service said done
    )


@dataclass(frozen=True)
class DiscoveredRow:
    native_identifier: str
    identifier_is_stable: bool
    title: str
    attributes: Mapping[str, Any]
    envelope: BoundingBox | None
    metadata_uri: str | None
    data_access_uri: str | None
    surveyed: str | None
    published: str | None
    vertical_datum_raw: str | None
    horizontal_datum_raw: str | None


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    authority: str
    family: SourceFamily
    serves: frozenset[Namespace]
    sensor: SensorType | None
    license_class: str
    completeness: Completeness
    discover: Callable[[BoundingBox, Transport], list[DiscoveredRow]] = field(
        repr=False, compare=False
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_BARE_LINK = re.compile(r"""https?://[^\s<>"']+""", re.IGNORECASE)


def first_link(value: Any) -> str | None:
    """The first web address an inventory field actually contains, or ``None``.

    Inventories publish "link" fields as whatever their own viewer renders:
    a bare address, an HTML fragment with one or several anchors, or a
    sentence such as "Will be available from ...".  Only a real address is
    usable as a source URI; the field itself stays verbatim in the row's
    attributes, so nothing the inventory said is lost.
    """

    text = _text(value)
    if text is None:
        return None
    candidates = _HREF.findall(text) or _BARE_LINK.findall(text)
    for candidate in candidates:
        link = html.unescape(candidate).strip()
        if link.lower().startswith(("https://", "http://")):
            return link
    return None


def _usiei_rows(
    layer: LidarInventoryLayer,
) -> Callable[[BoundingBox, Transport], list[DiscoveredRow]]:
    def discover(bbox: BoundingBox, transport: Transport) -> list[DiscoveredRow]:
        rows: list[DiscoveredRow] = []
        for page in fetch_all_usiei_pages(layer, bbox, transport=transport):
            for feature in page.features:
                attrs = feature.get("attributes")
                if not isinstance(attrs, Mapping):
                    raise ValueError(
                        "inventory feature is missing an attributes object"
                    )
                stable = None
                for key in ("GlobalID", "UUID", "InvID"):
                    if _text(attrs.get(key)):
                        stable = f"USIEI:{key}:{_text(attrs.get(key))}"
                        break
                local = _text(attrs.get("OBJECTID"))
                if stable is None and local is None:
                    raise ValueError("inventory feature carries no identifier at all")
                rows.append(
                    DiscoveredRow(
                        # OBJECTID is a row number local to one layer; it is
                        # kept so the row can be cited, and flagged so it is
                        # never used to equate records.
                        native_identifier=stable
                        or f"USIEI:LAYER{int(layer)}:OBJECTID:{local}",
                        identifier_is_stable=stable is not None,
                        title=_text(attrs.get("ProjectName"))
                        or "(untitled inventory record)",
                        attributes={str(k): v for k, v in attrs.items()},
                        envelope=esri_feature_envelope(feature),
                        metadata_uri=first_link(attrs.get("MetadataLink")),
                        data_access_uri=first_link(attrs.get("DataAccess")),
                        surveyed=_text(attrs.get("CollectionDate")),
                        published=None,
                        vertical_datum_raw=_text(attrs.get("VerticalDatum")),
                        horizontal_datum_raw=_text(attrs.get("HorizontalDatum")),
                    )
                )
        return rows

    return discover


def _ncei_rows(
    family: CatalogFamily,
) -> Callable[[BoundingBox, Transport], list[DiscoveredRow]]:
    def discover(bbox: BoundingBox, transport: Transport) -> list[DiscoveredRow]:
        rows: list[DiscoveredRow] = []
        for page in fetch_all_ncei_catalog_pages(family, bbox, transport=transport):
            for item in page.items:
                survey = (
                    _text(item.get("survey"))
                    or _text(item.get("surveyId"))
                    or _text(item.get("id"))
                )
                if survey is None:
                    raise ValueError("catalogue row carries no survey identifier")
                rows.append(
                    DiscoveredRow(
                        native_identifier=f"NCEI:{family.value}:{survey}",
                        identifier_is_stable=True,
                        title=survey,
                        attributes=dict(item),
                        envelope=None,
                        metadata_uri=None,
                        data_access_uri=None,
                        surveyed=_text(item.get("year"))
                        or _text(item.get("startDate")),
                        published=None,
                        vertical_datum_raw=None,
                        horizontal_datum_raw=None,
                    )
                )
        return rows

    return discover


def _nos_bag_rows(bbox: BoundingBox, transport: Transport) -> list[DiscoveredRow]:
    rows: list[DiscoveredRow] = []
    for page in fetch_all_nos_bag_pages(bbox, transport=transport):
        for feature in page.features:
            attrs = feature.get("attributes")
            if not isinstance(attrs, Mapping):
                raise ValueError(
                    "BAG inventory feature is missing an attributes object"
                )
            survey = _text(attrs.get("SURVEY_ID"))
            if survey is None:
                raise ValueError("BAG inventory feature carries no SURVEY_ID")
            rows.append(
                DiscoveredRow(
                    native_identifier=f"NOS:BAG:{survey}",
                    identifier_is_stable=True,
                    title=survey,
                    attributes={str(k): v for k, v in attrs.items()},
                    envelope=esri_feature_envelope(feature),
                    metadata_uri=None,
                    data_access_uri=first_link(attrs.get("DOWNLOAD_URL")),
                    surveyed=_text(attrs.get("SURVEY_YEAR")),
                    published=None,
                    vertical_datum_raw=None,
                    horizontal_datum_raw=None,
                )
            )
    return rows


_INLAND = frozenset({Namespace.ACCESS_POINT_INLAND})
_OFFSHORE = frozenset({Namespace.ACCESS_POINT_OFFSHORE})
_BOTH = _INLAND | _OFFSHORE
_NOAA_LICENSE = "US_GOVERNMENT_PUBLIC_DOMAIN"


def _providers() -> dict[str, ProviderSpec]:
    specs = [
        ProviderSpec(
            "USIEI_TOPOGRAPHIC_LIDAR",
            "NOAA Office for Coastal Management",
            SourceFamily.TERRESTRIAL_LIDAR_INVENTORY,
            _INLAND,
            None,
            _NOAA_LICENSE,
            Completeness.TRANSFER_LIMIT_FOLLOWED,
            _usiei_rows(LidarInventoryLayer.TOPOGRAPHIC),
        ),
        ProviderSpec(
            "USIEI_TOPOBATHY_LIDAR",
            "NOAA Office for Coastal Management",
            SourceFamily.TOPOBATHYMETRIC_LIDAR_INVENTORY,
            _BOTH,
            SensorType.TOPOBATHYMETRIC_LIDAR,
            _NOAA_LICENSE,
            Completeness.TRANSFER_LIMIT_FOLLOWED,
            _usiei_rows(LidarInventoryLayer.TOPOBATHY_SHORELINE),
        ),
        ProviderSpec(
            "USIEI_BATHYMETRIC_LIDAR",
            "NOAA Office for Coastal Management",
            SourceFamily.BATHYMETRIC_LIDAR_INVENTORY,
            _OFFSHORE,
            SensorType.BATHYMETRIC_LIDAR,
            _NOAA_LICENSE,
            Completeness.TRANSFER_LIMIT_FOLLOWED,
            _usiei_rows(LidarInventoryLayer.BATHYMETRIC),
        ),
        ProviderSpec(
            "USIEI_IFSAR",
            "NOAA Office for Coastal Management",
            SourceFamily.IFSAR_INVENTORY,
            _INLAND,
            None,
            _NOAA_LICENSE,
            Completeness.TRANSFER_LIMIT_FOLLOWED,
            _usiei_rows(LidarInventoryLayer.IFSAR),
        ),
        ProviderSpec(
            "USIEI_OTHER_BATHYMETRIC",
            "NOAA Office for Coastal Management",
            SourceFamily.OTHER_BATHYMETRIC_SURVEY_INVENTORY,
            _OFFSHORE,
            SensorType.DERIVED_BATHYMETRIC_GRID,
            _NOAA_LICENSE,
            Completeness.TRANSFER_LIMIT_FOLLOWED,
            _usiei_rows(LidarInventoryLayer.OTHER_BATHYMETRIC_SURVEYS),
        ),
        ProviderSpec(
            "NCEI_MULTIBEAM_CATALOG",
            "NOAA NCEI",
            SourceFamily.MULTIBEAM_SURVEY_CATALOG,
            _OFFSHORE,
            SensorType.MULTIBEAM_ECHOSOUNDER,
            _NOAA_LICENSE,
            Completeness.COUNT_CLOSED,
            _ncei_rows(CatalogFamily.MULTIBEAM),
        ),
        ProviderSpec(
            "NCEI_SOUNDING_CATALOG",
            "NOAA NCEI",
            SourceFamily.SOUNDING_SURVEY_CATALOG,
            _OFFSHORE,
            SensorType.HYDROGRAPHIC_SOUNDINGS,
            _NOAA_LICENSE,
            Completeness.COUNT_CLOSED,
            _ncei_rows(CatalogFamily.SOUNDING),
        ),
        ProviderSpec(
            "NOS_BAG_INVENTORY",
            "NOAA NCEI / Office of Coast Survey",
            SourceFamily.HYDROGRAPHIC_BAG_INVENTORY,
            _OFFSHORE,
            SensorType.MULTIBEAM_ECHOSOUNDER,
            _NOAA_LICENSE,
            Completeness.TRANSFER_LIMIT_FOLLOWED,
            _nos_bag_rows,
        ),
    ]
    return {spec.provider_id: spec for spec in specs}


PROVIDERS: Mapping[str, ProviderSpec] = _providers()


def providers_for(namespace: Namespace) -> list[ProviderSpec]:
    return [spec for spec in PROVIDERS.values() if namespace in spec.serves]


# -- discovery -------------------------------------------------------------


class RunState(StrEnum):
    PASS = "PASS"  # executed, rows returned, completeness proven
    ZERO = "ZERO"  # executed successfully, source reports none
    FAIL = "FAIL"  # executed and failed; says nothing about coverage
    NOT_AUTHORIZED = "NOT_AUTHORIZED"  # not executed
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class ProviderRun:
    provider_id: str
    family: SourceFamily
    state: RunState
    row_count: int
    request_count: int
    completeness: Completeness | None
    error: str | None
    rows: tuple[DiscoveredRow, ...] = field(repr=False, default=())
    responses: tuple[FrozenHttpResponse, ...] = field(repr=False, default=())


@dataclass(frozen=True)
class DiscoveryReceipt:
    bbox: BoundingBox
    namespace: Namespace
    discovered_utc: str
    authorization: Authorization
    runs: tuple[ProviderRun, ...]
    lifecycle: tuple[LifecycleStep, ...]

    @property
    def state(self) -> RunState:
        states = {run.state for run in self.runs}
        if not states or states == {RunState.NOT_RUN}:
            return RunState.NOT_RUN
        if RunState.FAIL in states:
            return RunState.FAIL
        if RunState.NOT_AUTHORIZED in states:
            return RunState.NOT_AUTHORIZED
        return RunState.PASS if RunState.PASS in states else RunState.ZERO

    @property
    def zero_result_claim_permitted(self) -> bool:
        """ "No sources exist here" may be said only if every provider ran clean."""

        return bool(self.runs) and all(run.state is RunState.ZERO for run in self.runs)

    def sources(self) -> list[SourceManifestation]:
        out: dict[str, SourceManifestation] = {}
        for run in self.runs:
            spec = PROVIDERS[run.provider_id]
            for row in run.rows:
                manifestation = to_source_manifestation(spec, row)
                out[manifestation.source_id] = manifestation
        return [out[key] for key in sorted(out)]

    def coverage(self) -> list[dict[str, Any]]:
        """Envelope relation of each discovered footprint to the query box.

        Envelope relations are for planning.  They are not polygon tests and
        cannot certify that a place was surveyed.
        """

        rows = []
        for run in self.runs:
            for row in run.rows:
                rows.append(
                    {
                        "provider_id": run.provider_id,
                        "family": run.family.value,
                        "native_identifier": row.native_identifier,
                        "identifier_is_stable": row.identifier_is_stable,
                        "title": row.title,
                        "envelope_relation": classify_bbox_relation(
                            self.bbox, row.envelope
                        ).value,
                        "surveyed": row.surveyed,
                        "vertical_datum_raw": row.vertical_datum_raw,
                        "basis": "ENVELOPE_ONLY_PLANNING",
                    }
                )
        rows.sort(key=lambda r: (r["provider_id"], r["native_identifier"]))
        return rows

    def to_document(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": "access_point_source_discovery_receipt/1.0",
            "contract_version": CONTRACT_VERSION,
            "acquisition_version": ACQUISITION_VERSION,
            "namespace": self.namespace.value,
            "bbox": [
                self.bbox.min_lon,
                self.bbox.min_lat,
                self.bbox.max_lon,
                self.bbox.max_lat,
            ],
            "dates": {
                "discovered_utc": self.discovered_utc,
                "note": "published, surveyed and retrieved dates are recorded per source",
            },
            "authorization": {
                "level": self.authorization.level.value,
                "granted_by": self.authorization.granted_by,
                "max_requests": self.authorization.max_requests,
            },
            "state": self.state.value,
            "zero_result_claim_permitted": self.zero_result_claim_permitted,
            "providers": [
                {
                    "provider_id": run.provider_id,
                    "family": run.family.value,
                    "state": run.state.value,
                    "row_count": run.row_count,
                    "request_count": run.request_count,
                    "completeness": (
                        None if run.completeness is None else run.completeness.value
                    ),
                    "error": run.error,
                    "requests": [response.manifest() for response in run.responses],
                }
                for run in self.runs
            ],
            "coverage": self.coverage(),
            "lifecycle": [
                {"state": s.state.value, "outcome": s.outcome.value, "detail": s.detail}
                for s in self.lifecycle
            ],
            "invariants": [
                "inventory coverage is not a depth or elevation measurement",
                "a failed provider says nothing about coverage",
                "envelope relations are planning-only",
                "no data product was downloaded by this run",
            ],
        }
        body["content_sha256"] = canonical_json_sha256(body)
        return body


def to_source_manifestation(
    spec: ProviderSpec, row: DiscoveredRow
) -> SourceManifestation:
    """An inventory row as a citable source.  Never a direct measurement."""

    uri = row.metadata_uri or row.data_access_uri
    return SourceManifestation(
        source_id=source_id(spec.provider_id, row.native_identifier, uri, None),
        provider=spec.provider_id,
        title=row.title,
        native_identifier=row.native_identifier,
        source_uri=uri,
        manifestation_sha256=None,
        retrieved_utc=None,
        published_date=row.published,
        survey_date=row.surveyed,
        # Only a stable identifier may act as a lineage root.
        lineage_root_id=row.native_identifier if row.identifier_is_stable else None,
        product_stage=ProductStage.DERIVED_PRODUCT,
        sensor_type=spec.sensor,
        coverage_state=CoverageState.UNKNOWN,
        provenance_state=ProvenanceState.REFERENCED_ONLY,
        license_note=spec.license_class,
    )


def discover_sources(
    namespace: Namespace,
    bbox: BoundingBox,
    *,
    discovered_utc: str,
    transport: Transport = denied_transport,
    authorization: Authorization | None = None,
    provider_ids: Sequence[str] | None = None,
) -> DiscoveryReceipt:
    """Metadata-only discovery of the sources that may cover a box.

    With no authorisation every provider is reported ``NOT_AUTHORIZED`` and no
    request is made.  A provider that fails is reported ``FAIL`` with its
    error; the others still run, and a zero-result claim stays forbidden.
    """

    auth = authorization if authorization is not None else Authorization()
    chosen = (
        [PROVIDERS[p] for p in provider_ids]
        if provider_ids is not None
        else providers_for(namespace)
    )
    for spec in chosen:
        if namespace not in spec.serves:
            raise ValueError(f"{spec.provider_id} does not serve {namespace.value}")
    log = LifecycleLog()
    runs: list[ProviderRun] = []

    if auth.level is not AuthorizationLevel.METADATA_DISCOVERY:
        log.record(
            LifecycleState.DISCOVER,
            StepOutcome.NOT_AUTHORIZED,
            "no metadata-discovery grant; no request was made",
        )
        runs = [
            ProviderRun(
                spec.provider_id,
                spec.family,
                RunState.NOT_AUTHORIZED,
                0,
                0,
                None,
                "not authorised",
            )
            for spec in chosen
        ]
        return DiscoveryReceipt(
            bbox, namespace, discovered_utc, auth, tuple(runs), log.steps
        )

    gate = budgeted(transport, auth)
    for spec in chosen:
        recorder = Recorder(gate)
        try:
            rows = spec.discover(bbox, recorder)
        except (AcquisitionNotAuthorized, RequestBudgetExceeded) as exc:
            runs.append(
                ProviderRun(
                    spec.provider_id,
                    spec.family,
                    RunState.NOT_AUTHORIZED,
                    0,
                    len(recorder.responses),
                    None,
                    str(exc),
                    responses=tuple(recorder.responses),
                )
            )
            continue
        except (
            Exception
        ) as exc:  # noqa: BLE001 - every source failure is reported, none hidden
            runs.append(
                ProviderRun(
                    spec.provider_id,
                    spec.family,
                    RunState.FAIL,
                    0,
                    len(recorder.responses),
                    None,
                    f"{type(exc).__name__}: {exc}",
                    responses=tuple(recorder.responses),
                )
            )
            continue
        ids = [row.native_identifier for row in rows]
        if len(ids) != len(set(ids)):
            runs.append(
                ProviderRun(
                    spec.provider_id,
                    spec.family,
                    RunState.FAIL,
                    0,
                    len(recorder.responses),
                    None,
                    "duplicate native identifier in one provider response",
                    responses=tuple(recorder.responses),
                )
            )
            continue
        runs.append(
            ProviderRun(
                spec.provider_id,
                spec.family,
                RunState.PASS if rows else RunState.ZERO,
                len(rows),
                len(recorder.responses),
                spec.completeness,
                None,
                rows=tuple(rows),
                responses=tuple(recorder.responses),
            )
        )

    failed = [run.provider_id for run in runs if run.state is RunState.FAIL]
    total = sum(run.row_count for run in runs)
    log.record(
        LifecycleState.DISCOVER,
        StepOutcome.FAIL if failed and total == 0 else StepOutcome.PASS,
        f"{len(runs)} providers queried, {total} rows, failed: {failed or 'none'}",
    )
    if not log.halted:
        log.record(
            LifecycleState.INSPECT_METADATA,
            StepOutcome.PASS,
            "inventory attributes kept verbatim",
        )
        unstable = sum(
            1 for run in runs for row in run.rows if not row.identifier_is_stable
        )
        log.record(
            LifecycleState.IDENTIFY_SOURCE,
            StepOutcome.PASS,
            f"{total - unstable} stable identifiers, {unstable} layer-local only",
        )
        log.record(
            LifecycleState.VALIDATE_SCOPE,
            StepOutcome.PASS,
            "footprint envelopes classified against the query box (planning only)",
        )
        log.record(
            LifecycleState.VERIFY_ACCESS,
            StepOutcome.PASS,
            "public catalogue endpoints answered",
        )
        log.record(
            LifecycleState.PLAN_ACQUISITION,
            StepOutcome.PASS,
            "candidate products listed; nothing scheduled",
        )
        log.record(
            LifecycleState.ACQUIRE_IF_AUTHORIZED,
            StepOutcome.NOT_AUTHORIZED,
            "data-product download is outside this module's grant",
        )
    return DiscoveryReceipt(
        bbox, namespace, discovered_utc, auth, tuple(runs), log.steps
    )
