"""Load the DEM platform catalog and account for every elevation registration.

``data_sources/elevation/dem_platform_catalog.yml`` (JSON-compatible YAML) holds
one entry per distinct product. Every place the repository registers an
elevation or bathymetry source is either an alias of a product or a classified
non-product registration.

``registration_universe()`` reads the registrations from the files listed in
``EXTRACTORS``. A new elevation registry must be added there; the catalog test
then fails until each of its registrations is accounted for.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "data_sources" / "elevation" / "dem_platform_catalog.yml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "dem_platform_catalog.schema.json"
PLATFORM_CLASSES = ("spaceborne", "airborne", "shipborne", "compiled")


@dataclass(frozen=True, order=True)
class Registration:
    path: str
    id: str


# -- extractors -----------------------------------------------------------------

def _json_records(text: str, list_key: str, id_key: str, keep: Callable[[dict], bool] = lambda r: True) -> set[str]:
    return {str(r[id_key]) for r in json.loads(text)[list_key] if keep(r)}


def _json_provider_keys(text: str, keep: Callable[[dict], bool]) -> set[str]:
    return {key for key, value in json.loads(text)["providers"].items() if keep(value)}


def _csv_ids(text: str) -> set[str]:
    return {row["dataset_id"] for row in csv.DictReader(io.StringIO(text))}


def _regex(pattern: str) -> Callable[[str], set[str]]:
    compiled = re.compile(pattern)
    return lambda text: set(compiled.findall(text))


def _tokens(*tokens: str) -> Callable[[str], set[str]]:
    return lambda text: {t for t in tokens if t in text}


def _yaml_provider_keys(text: str) -> set[str]:
    import yaml

    providers = yaml.safe_load(text)["providers"]
    return {k for k in providers if re.search(r"3dep|bathymetr|lidar|dem\b|elevation|terrain", k)}


_ELEVATION_INLAND_PROVIDERS = {"USIEI_TOPOGRAPHIC_LIDAR", "USGS_TNM_ELEVATION_PRODUCTS"}

EXTRACTORS: dict[str, Callable[[str], set[str]]] = {
    "data_sources/noaa/ncei_coastal_dems.yml": lambda t: _json_records(t, "datasets", "dataset_key"),
    "data/ncei_coastal_dem/registry/ncei_coastal_dem_priority_datasets.csv": _csv_ids,
    "data_sources/nasa/srtmgl1.yml": lambda t: _json_records(t, "datasets", "dataset_key"),
    "data_sources/opentopography/globaldem.yml": lambda t: _json_records(t, "demtypes", "demtype"),
    "pipeline/pr_marine_datasets.py": _regex(r'dataset_id="(\w+)"'),
    "registry/spatial/source_manifestations.json": lambda t: _json_records(
        t, "manifestations", "Dataset_ID", lambda r: r.get("Source_Family") == "USGS_3DEP"
    ),
    "configs/access_point_survey_runs.yaml": _regex(r'native_identifier:\s*"([^"]+)"'),
    "configs/location_query_providers.json": lambda t: _json_provider_keys(
        t, lambda p: p.get("family") in ("elevation", "bathymetry")
    ),
    "configs/spatial_dataset_providers.json": lambda t: _json_provider_keys(
        t, lambda p: "dem" in str(p.get("dataset_class", "")) or "bathymetr" in str(p.get("dataset_class", ""))
    ),
    "configs/remote_monitoring/providers.yaml": _yaml_provider_keys,
    "registry/access_points/inland.json": lambda t: _json_records(
        t, "sources", "source_id", lambda r: r.get("provider") in _ELEVATION_INLAND_PROVIDERS
    ),
    "registry/access_points/offshore.json": lambda t: {"sources"} if json.loads(t).get("sources") else set(),
    "spiderweb/access_points/acquisition.py": _regex(r'ProviderSpec\(\s*"(\w+)"'),
    "spiderweb/access_points/products.py": _regex(r'TNM_PROVIDER\s*=\s*"(\w+)"'),
    "pipeline/marine_lidar_sources.py": _tokens("USInteragencyElevInventory"),
    "pipeline/marine_sources.py": _tokens("next-catalogs", "nos_hydro_dynamic"),
    "scripts/run_ex1502l3_w00247_valid_overlap.py": _tokens("EX1502L3"),
    "scripts/run_ex1811_xyz_intersection.py": _tokens("EX1811"),
    "gebco/io.py": _tokens("GEBCO 2023"),
    "server/frontend/src/modules/SpatialIntelligence.tsx": _tokens("terrarium"),
    "server/frontend/src/spatial/runtime/CesiumRegionalRuntime.ts": _tokens("createGooglePhotorealistic3DTileset"),
}


def registration_universe(root: Path = REPO_ROOT) -> set[Registration]:
    universe: set[Registration] = set()
    for rel, extract in EXTRACTORS.items():
        text = (root / rel).read_text(encoding="utf-8")
        universe.update(Registration(rel, rid) for rid in extract(text))
    return universe


# -- catalog --------------------------------------------------------------------

def load_catalog(path: Path | str = CATALOG_PATH, *, validate: bool = True) -> dict:
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if validate:
        import jsonschema

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(catalog, schema, cls=jsonschema.Draft202012Validator)
    ids = [p["source_id"] for p in catalog["products"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate source_id: {', '.join(duplicates)}")
    return catalog


def products_by_id(catalog: Mapping) -> dict[str, dict]:
    return {p["source_id"]: p for p in catalog["products"]}


def group_by_platform_class(catalog: Mapping) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {cls: [] for cls in PLATFORM_CLASSES}
    for product in sorted(catalog["products"], key=lambda p: p["source_id"]):
        groups[product["platform_class"]].append(product)
    return groups


def alias_registrations(catalog: Mapping) -> dict[Registration, str]:
    """Map each alias registration to the product that claims it."""
    claimed: dict[Registration, str] = {}
    for product in catalog["products"]:
        for alias in product["aliases"]:
            reg = Registration(alias["path"], alias["id"])
            if reg in claimed:
                raise ValueError(f"{reg} is claimed by both {claimed[reg]} and {product['source_id']}")
            claimed[reg] = product["source_id"]
    return claimed


def non_product_registrations(catalog: Mapping) -> dict[Registration, str]:
    return {Registration(n["path"], n["id"]): n["classification"] for n in catalog["non_product_registrations"]}


@dataclass(frozen=True)
class Accounting:
    universe: frozenset[Registration]
    aliases: frozenset[Registration]
    non_products: frozenset[Registration]

    @property
    def unaccounted(self) -> tuple[Registration, ...]:
        return tuple(sorted(self.universe - self.aliases - self.non_products))

    @property
    def stale(self) -> tuple[Registration, ...]:
        """Catalog references that no extractor finds any more."""
        return tuple(sorted((self.aliases | self.non_products) - self.universe))

    @property
    def double_counted(self) -> tuple[Registration, ...]:
        return tuple(sorted(self.aliases & self.non_products))

    def as_dict(self) -> dict[str, object]:
        return {
            "registrations": len(self.universe),
            "files": len({r.path for r in self.universe}),
            "aliases": len(self.aliases & self.universe),
            "non_product_registrations": len(self.non_products & self.universe),
            "unaccounted": [r.__dict__ for r in self.unaccounted],
            "stale": [r.__dict__ for r in self.stale],
            "double_counted": [r.__dict__ for r in self.double_counted],
            "accounted_percent": round(
                100.0 * (len(self.universe) - len(self.unaccounted)) / len(self.universe), 2
            ) if self.universe else 100.0,
        }


def account(catalog: Mapping, root: Path = REPO_ROOT) -> Accounting:
    return Accounting(
        universe=frozenset(registration_universe(root)),
        aliases=frozenset(alias_registrations(catalog)),
        non_products=frozenset(non_product_registrations(catalog)),
    )


# -- record lookups used for datum parity and conflict checks ---------------------

def records(path: str, root: Path = REPO_ROOT) -> dict[str, dict]:
    """Records of a JSON dataset manifest (by dataset_key) or the NCEI CSV (by dataset_id)."""
    text = (root / path).read_text(encoding="utf-8")
    if path.endswith(".csv"):
        return {row["dataset_id"]: row for row in csv.DictReader(io.StringIO(text))}
    return {d["dataset_key"]: d for d in json.loads(text)["datasets"]}


def check_observation(obs: Mapping, root: Path = REPO_ROOT) -> bool:
    found = records(obs["path"], root)
    if obs["check"] == "present":
        return obs["id"] in found
    if obs["check"] == "absent":
        return obs["id"] not in found
    return obs["id"] in found and found[obs["id"]].get(obs["field"]) == obs["value"]


DATUM_MANIFESTS = (
    "data_sources/noaa/ncei_coastal_dems.yml",
    "data_sources/nasa/srtmgl1.yml",
    "data/ncei_coastal_dem/registry/ncei_coastal_dem_priority_datasets.csv",
)


def datum_parity_failures(catalog: Mapping, root: Path = REPO_ROOT) -> list[str]:
    """Authority aliases in dataset manifests must state the same vertical datum as the catalog."""
    failures = []
    for product in catalog["products"]:
        for alias in product["aliases"]:
            if not alias["authority"] or alias["path"] not in DATUM_MANIFESTS:
                continue
            stated = records(alias["path"], root)[alias["id"]].get("vertical_datum")
            if stated != product["vertical_datum_as_stated"]:
                failures.append(f"{product['source_id']}: catalog says {product['vertical_datum_as_stated']!r}, {alias['path']} says {stated!r}")
    return failures


def roots_of(product: Mapping, kinds: Iterable[str]) -> set[str]:
    wanted = set(kinds)
    return {r["root_id"] for r in product["acquisition_roots"] if r["kind"] in wanted}


def products_by_root(catalog: Mapping, kinds: Iterable[str] = ("measurement",)) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for product in catalog["products"]:
        for root_id in roots_of(product, kinds):
            index[root_id].append(product["source_id"])
    return dict(index)
