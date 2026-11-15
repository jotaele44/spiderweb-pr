"""Terminology namespaces for the access-point registries.

The acronym ``ILAP`` already carries several unrelated meanings in this
repository (a flight-track shape, an analytic "infrastructure-linked access
point" term, an investigation area/cluster ledger, a DEM screening score, a rail
source dataset, an enrichment hook) and ``OSAP`` appears only as an unexpanded
token in four operator-local ``FIC_OSAP_*`` source layers.  The two registries
introduced here -- Inland Access Points and Off-Shore Access Points -- are a
further, separate meaning.

Rules enforced by this module:

* every meaning has its own :class:`Namespace`; nothing is equal across
  namespaces, whatever the spelling of the identifier;
* the new registries never mint a machine identifier containing a legacy token
  (``ilap``, ``osap``, ``fic``, ``aasb``), because existing generators assign
  label, domain and bounding-box behaviour by substring;
* legacy identifiers are recognised and classified, never renamed or migrated.

See ``docs/ACCESS_POINT_TERMINOLOGY_DECISION.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from federation.spatial_core import canonical_json_sha256


class Namespace(StrEnum):
    """One value per distinct meaning.  Values are stable contract strings."""

    ACCESS_POINT_INLAND = "access_point.inland"
    ACCESS_POINT_OFFSHORE = "access_point.offshore"
    AVIATION_ILAP_PATH = "aviation.ilap_path"
    INVESTIGATION_ILAP_AREA = "investigation.ilap_area"
    INVESTIGATION_ILAP_CLUSTER = "investigation.ilap_cluster"
    ANALYTIC_ILAP_INFRASTRUCTURE_LINKED = "analytic.ilap_infrastructure_linked"
    SOURCE_FIC_OSAP = "source.fic_osap"
    TERRAIN_ILAP_SCORE = "terrain.ilap_score"
    SOURCE_FERROCARRIL_ILAP = "source.ferrocarril_ilap"
    ENRICHMENT_ILAP_CONTEXT = "enrichment.ilap_context"


REGISTRY_NAMESPACES: frozenset[Namespace] = frozenset(
    {Namespace.ACCESS_POINT_INLAND, Namespace.ACCESS_POINT_OFFSHORE}
)

LEGACY_NAMESPACES: frozenset[Namespace] = frozenset(Namespace) - REGISTRY_NAMESPACES

# Short registry codes.  Chosen because neither string occurred anywhere in the
# repository before this package was added.
REGISTRY_CODE: dict[Namespace, str] = {
    Namespace.ACCESS_POINT_INLAND: "INAP",
    Namespace.ACCESS_POINT_OFFSHORE: "OFAP",
}

REGISTRY_TITLE: dict[Namespace, str] = {
    Namespace.ACCESS_POINT_INLAND: "Inland Access Points",
    Namespace.ACCESS_POINT_OFFSHORE: "Off-Shore Access Points",
}


class IdentifierKind(StrEnum):
    FEATURE = "FEATURE"
    OBSERVATION = "OBSERVATION"
    SOURCE_MANIFESTATION = "SOURCE_MANIFESTATION"
    DERIVED_GEOMETRY = "DERIVED_GEOMETRY"
    RELATIONSHIP = "RELATIONSHIP"
    PROVISIONAL_LABEL = "PROVISIONAL_LABEL"
    LEGACY = "LEGACY"


class NamespaceCollisionError(ValueError):
    """Raised when records from different namespaces are treated as one thing."""


class ReservedTokenError(ValueError):
    """Raised when a new machine identifier would reuse a legacy token."""


@dataclass(frozen=True, slots=True)
class TypedRef:
    """An identifier that is only meaningful together with its namespace."""

    namespace: Namespace
    identifier: str

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, Namespace):
            raise TypeError("namespace must be a Namespace")
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("identifier must be a non-empty string")

    def __str__(self) -> str:
        return f"{self.namespace.value}:{self.identifier}"


_FEATURE_RE = {
    Namespace.ACCESS_POINT_INLAND: re.compile(r"^INAP-PR-[0-9]{6}$"),
    Namespace.ACCESS_POINT_OFFSHORE: re.compile(r"^OFAP-PR-[0-9]{6}$"),
}
_OBSERVATION_RE = {
    Namespace.ACCESS_POINT_INLAND: re.compile(r"^INAP-OBS-[0-9a-f]{16}$"),
    Namespace.ACCESS_POINT_OFFSHORE: re.compile(r"^OFAP-OBS-[0-9a-f]{16}$"),
}
_SOURCE_RE = re.compile(r"^APSRC-[0-9a-f]{16}$")
_GEOMETRY_RE = re.compile(r"^APGEO-[0-9a-f]{16}$")
_RELATIONSHIP_RE = re.compile(r"^APREL-[0-9a-f]{16}$")

# Operator-supplied provisional labels.  They are raw source labels, not
# identities: they classify into the off-shore registry namespace with kind
# PROVISIONAL_LABEL and can never be used as a feature id.
_PROVISIONAL_LABEL_RE = re.compile(r"^OSAP-SEED-[0-9]{3}$")

# Legacy patterns, most specific first.  Each maps a spelling to the meaning it
# has in the existing repository artefacts.
_LEGACY_PATTERNS: tuple[tuple[re.Pattern[str], Namespace], ...] = (
    (re.compile(r"^ILAP_AREA_[A-Z0-9_]+$"), Namespace.INVESTIGATION_ILAP_AREA),
    (re.compile(r"^ILAP_CLUSTER_[A-Z0-9_]+$"), Namespace.INVESTIGATION_ILAP_CLUSTER),
    (re.compile(r"^ilap_(area|cluster)_id$"), Namespace.INVESTIGATION_ILAP_CLUSTER),
    (re.compile(r"^FERRO-[0-9]{4,}$"), Namespace.SOURCE_FERROCARRIL_ILAP),
    (re.compile(r"^ferrocarril_ilap_"), Namespace.SOURCE_FERROCARRIL_ILAP),
    (re.compile(r"^(?i:fic_osap)"), Namespace.SOURCE_FIC_OSAP),
    (re.compile(r"^PIN_AC_FICOSAP[A-Z0-9]*(_[0-9]{6})?$"), Namespace.SOURCE_FIC_OSAP),
    (re.compile(r"^OSAP_(to_ILAP|Primary_to_Secondary|Primary_Ring)$"), Namespace.SOURCE_FIC_OSAP),
    (re.compile(r"^(ILAP_SCORE|ilap_score|ILAP_anomalies|ilap_dem_anomalies)$"), Namespace.TERRAIN_ILAP_SCORE),
    (re.compile(r"^PIN_AC_ILAPDEMANO(_[0-9]{6})?$"), Namespace.TERRAIN_ILAP_SCORE),
    (re.compile(r"^ilap_context(_distance_m)?$"), Namespace.ENRICHMENT_ILAP_CONTEXT),
    (re.compile(r"^SW-ALL-[0-9]{7}$"), Namespace.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    (re.compile(r"^(ilap_constructs|ilap_master_nodes|ilap_predictions)$"), Namespace.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    (re.compile(r"^PIN_AC_ILAP(MASTER|PREDIC)(_[0-9]{6})?$"), Namespace.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    (re.compile(r"^(ilap_id|ilap_type|ilap_subtype|ilap_class|ilap_subcategory|ilap_type_calc)$"), Namespace.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    (re.compile(r"^ILAP-(Urban|Coastal|Hydro-Karst|Ridge)$"), Namespace.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    # skywatcher-pr's governed threshold registry owns identifiers of the form
    # ILAP-WEIGHT-*, ILAP-INFRA-*NM, ILAP-GRID-0.05DEG, ILAP-OVERALL-*, ...
    (re.compile(r"^ILAP-[A-Z0-9.-]+$"), Namespace.AVIATION_ILAP_PATH),
    (re.compile(r"^ilap_status$"), Namespace.AVIATION_ILAP_PATH),
    (re.compile(r"^airspace_ilap_candidates(\.geojson|\.kml)?$"), Namespace.AVIATION_ILAP_PATH),
    (re.compile(r"^ilap_corridor_candidate$"), Namespace.AVIATION_ILAP_PATH),
    # The aviation bridge writes corridor ids as ``ILAP_<flight_id>``.  This is
    # deliberately last: the AREA / CLUSTER forms above are more specific.
    (re.compile(r"^ILAP_.+$"), Namespace.AVIATION_ILAP_PATH),
)

# The bare lowercase string "ilap" is the aviation bridge's ``candidate_type``
# value.  The bare uppercase acronym has no single meaning and is refused.
_BARE_AVIATION_CANDIDATE_TYPE = "ilap"
_AMBIGUOUS_BARE = frozenset({"ILAP", "OSAP", "Ilap", "Osap", "osap", "FIC", "fic"})

_RESERVED_TOKENS = ("ilap", "osap", "fic", "aasb")
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Classification:
    namespace: Namespace
    kind: IdentifierKind


def classify_identifier(value: str) -> Classification | None:
    """Return the namespace an identifier belongs to, or ``None`` if unknown.

    ``None`` means "this module makes no claim"; it never means "safe to treat
    as an access point".  Ambiguous bare acronyms raise, because guessing a
    meaning for them is exactly the failure this module exists to prevent.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("identifier must be a non-empty string")
    text = value.strip()
    if text in _AMBIGUOUS_BARE:
        raise NamespaceCollisionError(
            f"{text!r} is ambiguous: it names several unrelated things in this "
            "repository; use a namespaced identifier"
        )
    for namespace, pattern in _FEATURE_RE.items():
        if pattern.match(text):
            return Classification(namespace, IdentifierKind.FEATURE)
    for namespace, pattern in _OBSERVATION_RE.items():
        if pattern.match(text):
            return Classification(namespace, IdentifierKind.OBSERVATION)
    if _PROVISIONAL_LABEL_RE.match(text):
        return Classification(Namespace.ACCESS_POINT_OFFSHORE, IdentifierKind.PROVISIONAL_LABEL)
    if text == _BARE_AVIATION_CANDIDATE_TYPE:
        return Classification(Namespace.AVIATION_ILAP_PATH, IdentifierKind.LEGACY)
    for pattern, namespace in _LEGACY_PATTERNS:
        if pattern.match(text):
            return Classification(namespace, IdentifierKind.LEGACY)
    return None


def is_feature_id(value: str, namespace: Namespace) -> bool:
    pattern = _FEATURE_RE.get(namespace)
    return bool(pattern and isinstance(value, str) and pattern.match(value))


def is_observation_id(value: str, namespace: Namespace) -> bool:
    pattern = _OBSERVATION_RE.get(namespace)
    return bool(pattern and isinstance(value, str) and pattern.match(value))


def is_source_id(value: str) -> bool:
    return isinstance(value, str) and bool(_SOURCE_RE.match(value))


def is_geometry_id(value: str) -> bool:
    return isinstance(value, str) and bool(_GEOMETRY_RE.match(value))


def is_relationship_id(value: str) -> bool:
    return isinstance(value, str) and bool(_RELATIONSHIP_RE.match(value))


def require_registry_namespace(namespace: Namespace) -> Namespace:
    if namespace not in REGISTRY_NAMESPACES:
        raise NamespaceCollisionError(
            f"{namespace!r} is a legacy meaning, not an access-point registry"
        )
    return namespace


def feature_id(namespace: Namespace, sequence: int) -> str:
    """Opaque sequence identifier.  Carries no location, name or class."""

    require_registry_namespace(namespace)
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise TypeError("sequence must be an integer")
    if not 1 <= sequence <= 999_999:
        raise ValueError("sequence must be within 1..999999")
    return f"{REGISTRY_CODE[namespace]}-PR-{sequence:06d}"


def feature_sequence(identifier: str, namespace: Namespace) -> int:
    if not is_feature_id(identifier, namespace):
        raise NamespaceCollisionError(
            f"{identifier!r} is not a feature id of {namespace.value}"
        )
    return int(identifier.rsplit("-", 1)[1])


def _digest16(payload: object) -> str:
    return canonical_json_sha256(payload)[:16]


def source_id(provider: str, native_identifier: str | None, source_uri: str | None,
              manifestation_sha256: str | None) -> str:
    """Identity of one source manifestation (one exact published thing).

    Two downloads of byte-identical content from the same provider record share
    an id; a revised file under the same native identifier does not.
    """

    if not provider or not provider.strip():
        raise ValueError("provider is required")
    if not (native_identifier or source_uri or manifestation_sha256):
        raise ValueError("a source needs a native identifier, a URI or a content hash")
    return "APSRC-" + _digest16(
        {
            "provider": provider.strip(),
            "native_identifier": native_identifier,
            "source_uri": source_uri,
            "sha256": manifestation_sha256,
        }
    )


def observation_id(namespace: Namespace, source: str, native_record_id: str) -> str:
    """Identity of one original observation inside one source manifestation."""

    require_registry_namespace(namespace)
    if not is_source_id(source):
        raise ValueError("source must be a source-manifestation id")
    if not native_record_id or not str(native_record_id).strip():
        raise ValueError("native_record_id is required; identity is never positional")
    return f"{REGISTRY_CODE[namespace]}-OBS-" + _digest16(
        {"namespace": namespace.value, "source": source, "native": str(native_record_id).strip()}
    )


def geometry_id(observation_ids: tuple[str, ...], method: str, method_version: str,
                geometry_logical_sha256: str) -> str:
    if not observation_ids:
        raise ValueError("a derived geometry must cite at least one observation")
    return "APGEO-" + _digest16(
        {
            "observations": sorted(observation_ids),
            "method": method,
            "method_version": method_version,
            "geometry": geometry_logical_sha256,
        }
    )


def relationship_id(relationship_type: str, source_ref: TypedRef, target_ref: TypedRef,
                    connectivity_kind: str | None) -> str:
    return "APREL-" + _digest16(
        {
            "type": relationship_type,
            "source": str(source_ref),
            "target": str(target_ref),
            "kind": connectivity_kind,
        }
    )


def same_identity(a: TypedRef, b: TypedRef) -> bool:
    """Identity requires the same namespace *and* the same identifier."""

    return a.namespace is b.namespace and a.identifier == b.identifier


def require_same_namespace(a: TypedRef, b: TypedRef) -> None:
    if a.namespace is not b.namespace:
        raise NamespaceCollisionError(
            f"{a} and {b} belong to different namespaces and cannot be merged, "
            "matched or deduplicated against each other"
        )


def typed_ref(value: str, namespace: Namespace | None = None) -> TypedRef:
    """Build a :class:`TypedRef`, refusing a namespace the spelling contradicts."""

    found = classify_identifier(value)
    if namespace is None:
        if found is None:
            raise NamespaceCollisionError(
                f"cannot determine the namespace of {value!r}; state it explicitly"
            )
        return TypedRef(found.namespace, value)
    if found is not None and found.namespace is not namespace:
        raise NamespaceCollisionError(
            f"{value!r} is spelled as {found.namespace.value}, not {namespace.value}"
        )
    return TypedRef(namespace, value)


def validate_new_machine_identifier(value: str) -> str:
    """Refuse legacy tokens in any *new* layer id, schema id, field or enum name.

    Existing generators assign the manifest domain ``ilap`` to any layer id
    containing that substring, disable the land bounding-box filter for ids
    starting ``fic_osap``, and rewrite the tokens into acronyms in labels.  A
    new identifier that trips those rules silently inherits legacy behaviour.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("identifier must be a non-empty string")
    lowered = value.strip().lower()
    if "ilap" in lowered:
        raise ReservedTokenError(f"{value!r} contains the reserved substring 'ilap'")
    tokens = [token for token in _TOKEN_SPLIT.split(lowered) if token]
    for token in tokens:
        if token in _RESERVED_TOKENS:
            raise ReservedTokenError(f"{value!r} contains the reserved token {token!r}")
    if lowered.startswith(("fic_osap", "aasb")):
        raise ReservedTokenError(f"{value!r} starts with a reserved legacy prefix")
    return value.strip()
