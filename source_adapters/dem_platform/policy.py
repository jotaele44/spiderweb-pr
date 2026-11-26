"""Merge policy for DEM sources by acquisition platform.

Sources measured by different platforms see different surfaces (radar
scattering surface, optical first surface, lidar bare earth, sonar seafloor), at
different epochs and on different vertical datums. They are kept as separate
layers unless the selection is one verified platform class, one surface model
and one declared vertical datum. Compiled products are never merged with others
as if they were independent measurements.

Two products on one leveled datum can still differ by how they reached it: a
lidar survey turns GNSS ellipsoidal heights into PRVD02 heights through a hybrid
geoid model, and the 2018 and D24 surveys used different ones (GEOID12B and
GEOID18). Such products stay in one group but as separate layers, one per geoid
realization, so their difference can be measured before anything is merged.

Independence for corroboration is decided on canonical acquisition roots, not on
platform names: NASA's records call the same 2000 Shuttle flight STS-99
(SRTMGL1) and OV-105 (NASADEM).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

from .catalog import roots_of

UNDECLARED_DATUMS = frozenset({"undeclared"})
UNDECLARED_GEOID = "undeclared"
DEPENDENCY_KINDS = ("measurement", "fill")


def geoid_of(product: Mapping) -> str:
    return product.get("geoid_model") or UNDECLARED_GEOID


@dataclass(frozen=True)
class PlatformPolicyResult:
    source_ids: tuple[str, ...]
    platform_classes: tuple[str, ...]
    surface_models: tuple[str, ...]
    vertical_datums: tuple[str, ...]
    merge_policy: str
    review_status: str
    reasons: tuple[str, ...]
    geoid_models: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(self).items()}


def evaluate_platform_mix(products: Sequence[Mapping]) -> PlatformPolicyResult:
    ids = tuple(p["source_id"] for p in products)
    classes = tuple(sorted({p["platform_class"] for p in products}))
    surfaces = tuple(sorted({p["surface_model"] for p in products}))
    datums = tuple(sorted({p["vertical_datum"] for p in products}))
    geoids = tuple(sorted({geoid_of(p) for p in products}))
    if not products:
        return PlatformPolicyResult((), (), (), (), "no_sources", "review_required", ("no sources selected",))

    reasons: list[str] = []
    for p in products:
        if p["platform_status"] != "verified":
            reasons.append(f"{p['source_id']}: platform not verified from provider metadata")
        if p["vertical_datum"] in UNDECLARED_DATUMS:
            reasons.append(f"{p['source_id']}: vertical datum undeclared")
    if len(products) > 1:
        compiled = [p["source_id"] for p in products if p["platform_class"] == "compiled"]
        if compiled:
            reasons.append("compiled products cannot be merged as independent measurements: " + ", ".join(compiled))
        if len(classes) > 1:
            reasons.append("mixed platform classes: " + ", ".join(classes))
        if len(surfaces) > 1:
            reasons.append("mixed surface models: " + ", ".join(surfaces))
        if len(datums) > 1:
            reasons.append("mixed vertical datums: " + ", ".join(datums))

    if reasons:
        return PlatformPolicyResult(ids, classes, surfaces, datums, "separate_layers_until_harmonization", "review_required",
                                    tuple(reasons), geoids)
    if len(products) > 1 and len(geoids) > 1:
        note = (f"{datums[0]} realized with {', '.join(geoids)}: keep one layer per geoid realization "
                "and difference them before any merge")
        return PlatformPolicyResult(ids, classes, surfaces, datums, "same_datum_separate_geoid_layers", "pass", (), geoids, (note,))
    policy = "single_source" if len(products) == 1 else "same_platform_class_same_surface_same_datum"
    return PlatformPolicyResult(ids, classes, surfaces, datums, policy, "pass", (), geoids)


def layer_groups(products: Sequence[Mapping]) -> dict[tuple[str, str, str], dict[str, tuple[str, ...]]]:
    """Group products by (platform class, surface model, vertical datum); within a group, one layer per geoid."""
    groups: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for p in products:
        key = (p["platform_class"], p["surface_model"], p["vertical_datum"])
        groups.setdefault(key, {}).setdefault(geoid_of(p), []).append(p["source_id"])
    return {k: {g: tuple(ids) for g, ids in sorted(layers.items())} for k, layers in sorted(groups.items())}


def shared_acquisition_roots(a: Mapping, b: Mapping, kinds: Iterable[str] = DEPENDENCY_KINDS) -> tuple[str, ...]:
    """Roots both products depend on. Empty means they corroborate independently."""
    kinds = tuple(kinds)
    return tuple(sorted(roots_of(a, kinds) & roots_of(b, kinds)))


def independent(a: Mapping, b: Mapping) -> bool:
    return not shared_acquisition_roots(a, b)


def geolocation_dependencies(product: Mapping, provider_ref: str) -> tuple[dict, ...]:
    """Products such as Landsat that use this DEM only to place pixels."""
    return tuple(
        c for c in product["consumed_by"]
        if c["provider_ref"] == provider_ref and c["dependency_kind"] == "geolocation"
    )


def pairwise_independence(products: Sequence[Mapping]) -> list[dict[str, object]]:
    rows = []
    for i, a in enumerate(products):
        for b in products[i + 1:]:
            shared = shared_acquisition_roots(a, b)
            rows.append({"a": a["source_id"], "b": b["source_id"], "independent": not shared, "shared_roots": list(shared)})
    return rows
