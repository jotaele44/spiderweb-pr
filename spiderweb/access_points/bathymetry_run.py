"""A declared, reproducible run over one gridded seabed survey.

The off-shore counterpart of :mod:`survey_run`, with the same two halves:

* :func:`extract` needs the held product (never committed).  It checks the
  file against its download manifest and against the hash the run declares,
  then writes the small pieces that *are* committed: a lossless two-band
  subset (elevation and the product's own per-cell uncertainty), a copy of the
  download manifest, and the facts read from the product's metadata.
* :func:`build_report` needs only what is committed, and must give the same
  sealed report to anyone who re-runs it.

Two things differ from an inland run, both on purpose:

* **There is no target record.**  No off-shore record holds a position, so the
  run is not centred on one and reports no distance to one.  The only place
  named is an analyst search area, and the report says how the survey's extent
  relates to it -- as a search area, never as a feature position.
* **The uncertainty is the product's own, cell by cell**, not one figure for a
  whole project.  It sets what can be seen: a depression that nowhere exceeds
  the uncertainty of its own cells is not reported at all, and one that
  exceeds it only narrowly stays a candidate.

A run changes no registry record.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml

from federation.spatial_core import canonical_json_sha256
from gebco.marine_evidence import SensorType
from pipeline.marine_alternate_products import parse_nos_product_links

from . import CONTRACT_VERSION, survey
from .acquisition import replay_transport
from .detection import DetectionParameters, EvaluationState
from .discovery import load_corridor_config
from .namespaces import Namespace
from .products import MANIFEST_SCHEMA, ProductRequest, held_product
from .survey_run import RUNS_VERSION, SURVEY_DIR

RUNS_KEY = "seabed_runs"
CORRIDORS_PATH = "configs/access_point_discovery_corridors.yaml"
NOS_BAG_PROVIDER = "NOS_BAG_PRODUCT"
POINTER_NAME = "CURRENT_SEABED.json"
POINTER_SCHEMA = "access_point_seabed_pointer/1.0"
REPORT_NAME = "seabed_report.json"
REPORT_SCHEMA = "access_point_seabed_report/1.0"
FACTS_NAME = "product_facts.json"
FACTS_SCHEMA = "access_point_seabed_product_facts/1.0"
SUBSET_NAME = "subsets/base_grid.tif"
_HEX = set("0123456789abcdef")


class SeabedRunError(ValueError):
    """The run configuration or its committed evidence is not usable."""


def load_run(config_path: str | Path, run_id: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("version") != RUNS_VERSION:
        raise SeabedRunError(f"{config_path}: unsupported survey-run file")
    for run in data.get(RUNS_KEY) or []:
        if str(run.get("run_id")) == run_id:
            return _validated(dict(run))
    raise SeabedRunError(f"no seabed run {run_id!r} is declared")


def _validated(run: dict[str, Any]) -> dict[str, Any]:
    forbidden = sorted(
        set(run)
        & {
            "center",
            "centre",
            "lon",
            "lat",
            "coordinates",
            "geometry",
            "bbox",
            "target_feature",
        }
    )
    if forbidden:
        raise SeabedRunError(
            f"a seabed run may not state a position or a target record ({forbidden}); "
            "it names a declared search area and nothing else"
        )
    try:
        namespace = Namespace(run["registry"])
    except (KeyError, ValueError) as exc:
        raise SeabedRunError("a run must name a registry") from exc
    if namespace is not Namespace.ACCESS_POINT_OFFSHORE:
        raise SeabedRunError("a seabed run belongs to the off-shore registry")
    run["registry"] = namespace
    if not str(run.get("search_area") or "").strip():
        raise SeabedRunError("a run must name the search area it is read against")
    parameters = run.get("parameters") or {}
    if "nested" not in parameters:
        raise SeabedRunError(
            "a run must say whether nested basins are reported (parameters.nested)"
        )
    run["parameters"] = DetectionParameters(
        min_depth_m=float(parameters["min_depth_m"]),
        min_area_m2=float(parameters["min_area_m2"]),
        nested=bool(parameters["nested"]),
    )
    product = run.get("product")
    if not isinstance(product, Mapping):
        raise SeabedRunError("a run must describe exactly one product")
    product = dict(product)
    for key in (
        "filename",
        "native_identifier",
        "landing_page",
        "stated_vertical_datum",
        "lineage_root_id",
    ):
        if not str(product.get(key) or "").strip():
            raise SeabedRunError(f"product: {key} is required")
    digest = str(product.get("sha256") or "")
    if len(digest) != 64 or not set(digest) <= _HEX:
        raise SeabedRunError("product: sha256 must be the 64-digit hash of the file")
    for key in ("vertical_statement_basis", "vertical_uncertainty_basis"):
        text = " ".join(str(product.get(key) or "").split())
        if not text:
            raise SeabedRunError(f"product: {key} must say where the value was read")
        product[key] = text
    run["product"] = product
    return run


def _run_dir(repo_root: Path, run: Mapping[str, Any]) -> Path:
    return repo_root / SURVEY_DIR / str(run["run_id"])


def _request(repo_root: Path, run: Mapping[str, Any]) -> ProductRequest:
    """The product as the survey's frozen landing page lists it.  No network."""

    product = run["product"]
    transport = replay_transport(_run_dir(repo_root, run) / "catalogue")
    page = parse_nos_product_links(transport(product["landing_page"]))
    for link in page.assets:
        url = str(link["url"])
        if url.rsplit("/", 1)[-1] == product["filename"]:
            return ProductRequest(
                provider=NOS_BAG_PROVIDER,
                native_identifier=product["native_identifier"],
                title=product["filename"],
                url=url,
                metadata_uri=product["landing_page"],
            )
    raise SeabedRunError(
        f"{product['filename']} is not listed on the frozen landing page"
    )


def _source(
    request: ProductRequest, product: Mapping[str, Any], sha256: str, retrieved_utc: str
) -> Any:
    return survey.gridded_source(
        provider=NOS_BAG_PROVIDER,
        native_identifier=request.native_identifier,
        title=request.title,
        source_uri=request.url,
        sha256=sha256,
        retrieved_utc=retrieved_utc,
        published_date=None,
        survey_date=product.get("survey_date"),
        lineage_root_id=product["lineage_root_id"],
        sensor_type=SensorType.MULTIBEAM_ECHOSOUNDER,
    )


def _write_json(path: Path, document: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sealed(path: Path, schema: str) -> dict[str, Any]:
    if not path.is_file():
        raise SeabedRunError(f"{path.name} is missing")
    document = json.loads(path.read_text(encoding="utf-8"))
    body = dict(document)
    stated = body.pop("content_sha256", None)
    if document.get("schema") != schema or canonical_json_sha256(body) != stated:
        raise SeabedRunError(f"{path.name} does not match its content hash")
    return document


def extract(
    run: Mapping[str, Any], *, repo_root: str | Path, product_dir: str | Path
) -> dict[str, Any]:
    """Write the committed pieces from the held product.  No network."""

    root = Path(repo_root)
    run_dir = _run_dir(root, run)
    product = run["product"]
    request = _request(root, run)
    held = held_product(request, product_dir)
    if held is None:
        raise SeabedRunError(f"{product['filename']} is not held in {product_dir}")
    if held.sha256 != product["sha256"]:
        raise SeabedRunError(
            f"{product['filename']} is held, but its hash is not the one the run declares"
        )
    (run_dir / "products").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        Path(product_dir) / (product["filename"] + ".manifest.json"),
        run_dir / "products" / (product["filename"] + ".manifest.json"),
    )
    grid = survey.read_depth_grid(held.path)
    subset_sha256 = survey.write_depth_subset(grid, run_dir / SUBSET_NAME)
    body: dict[str, Any] = {
        "schema": FACTS_SCHEMA,
        "run_id": run["run_id"],
        "parent_sha256": held.sha256,
        "subset_file": SUBSET_NAME,
        "subset_sha256": subset_sha256,
        "read_from": "the held product's own metadata; not recomputable from the subset",
        "facts": grid.facts,
        "layers_read": "the base grid only (elevation and uncertainty)",
    }
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    _write_json(run_dir / FACTS_NAME, body)
    return {"subset_sha256": subset_sha256, "facts": body}


def _manifest(run_dir: Path, filename: str) -> dict[str, Any]:
    path = run_dir / "products" / (filename + ".manifest.json")
    if not path.is_file():
        raise SeabedRunError(f"no download manifest is committed for {filename}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise SeabedRunError(f"{path.name} is not a product manifest")
    return manifest


def search_area_relation(
    repo_root: Path, run: Mapping[str, Any], extent: Mapping[str, Any]
) -> dict[str, Any]:
    """How the survey's covered extent sits against the declared search area."""

    config = load_corridor_config(repo_root / CORRIDORS_PATH)
    for entry in config["corridors"]:
        if entry.get("corridor_id") == run["search_area"]:
            break
    else:
        raise SeabedRunError(f"search area {run['search_area']!r} is not declared")
    if Namespace(entry["registry"]) is not run["registry"]:
        raise SeabedRunError("the search area belongs to the other registry")
    area = [float(v) for v in entry["bbox"]]
    covered = extent["covered_bbox_lonlat"]
    if covered is None:
        relation = "NO_COVERED_CELLS"
    elif (
        area[0] <= covered[0]
        and area[1] <= covered[1]
        and covered[2] <= area[2]
        and covered[3] <= area[3]
    ):
        relation = "FULLY_WITHIN"
    elif (
        covered[2] < area[0]
        or covered[0] > area[2]
        or covered[3] < area[1]
        or covered[1] > area[3]
    ):
        relation = "OUTSIDE"
    else:
        relation = "PARTLY_WITHIN"
    return {
        "search_area": run["search_area"],
        "search_area_bbox_lonlat": area,
        "search_area_is": (
            "an analyst-drawn box for finding sources; not the position of any "
            "feature or seed"
        ),
        **extent,
        "relation": relation,
    }


def prior_receipt_check(
    repo_root: Path,
    product: Mapping[str, Any],
    manifest: Mapping[str, Any],
    surface: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Compare with an earlier, independently produced receipt for the same file.

    The earlier receipt was made by different code on a different day.  Where
    the two agree, the bytes and the reading of them are both confirmed.
    """

    relative = product.get("prior_receipt")
    if not relative:
        return None
    path = repo_root / str(relative)
    if not path.is_file():
        raise SeabedRunError(f"the prior receipt {relative} is missing")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    for bag in receipt.get("bags") or []:
        if bag.get("filename") == product["filename"]:
            break
    else:
        raise SeabedRunError(f"{relative} does not describe {product['filename']}")
    raster = bag.get("raster") or {}
    uncertainty = surface["cell_uncertainty_m"] or {}

    def close(a: Any, b: Any) -> bool | None:
        if a is None or b is None:
            return None
        return abs(float(a) - float(b)) <= 5e-4

    comparisons = {
        "sha256": bag.get("sha256") == manifest["response_sha256"],
        "size_bytes": bag.get("size_bytes") == manifest["response_size"],
        "valid_cells": raster.get("valid_cells") == surface["valid_cells"],
        "elevation_min_m": close(
            (raster.get("elevation_m") or {}).get("minimum"), surface["elevation_min_m"]
        ),
        "elevation_max_m": close(
            (raster.get("elevation_m") or {}).get("maximum"), surface["elevation_max_m"]
        ),
        "uncertainty_min_m": close(
            (raster.get("uncertainty_m") or {}).get("minimum"), uncertainty.get("min")
        ),
        "uncertainty_max_m": close(
            (raster.get("uncertainty_m") or {}).get("maximum"), uncertainty.get("max")
        ),
    }
    return {
        "receipt": str(relative),
        "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "receipt_state": receipt.get("state"),
        "receipt_aoi_relation": bag.get("aoi_relation"),
        "receipt_vertical_reference": receipt.get("vertical_reference"),
        "agrees": comparisons,
        "all_agree": all(value is True for value in comparisons.values()),
    }


def build_report(run: Mapping[str, Any], *, repo_root: str | Path) -> dict[str, Any]:
    """The sealed report, computed from committed evidence only."""

    root = Path(repo_root)
    run_dir = _run_dir(root, run)
    product = run["product"]
    request = _request(root, run)
    manifest = _manifest(run_dir, product["filename"])
    if manifest["request"]["url"] != request.url:
        raise SeabedRunError(
            "the download manifest names a different address than the landing page"
        )
    if manifest["response_sha256"] != product["sha256"]:
        raise SeabedRunError(
            "the download manifest's hash is not the one the run declares"
        )
    facts = _sealed(run_dir / FACTS_NAME, FACTS_SCHEMA)
    if facts["parent_sha256"] != product["sha256"]:
        raise SeabedRunError("the product facts were read from a different file")
    subset_path = run_dir / SUBSET_NAME
    if not subset_path.is_file():
        raise SeabedRunError("the base-grid subset is missing")
    subset_sha256 = survey.sha256_file(subset_path)
    if subset_sha256 != facts["subset_sha256"]:
        raise SeabedRunError(
            "the base-grid subset does not match the hash recorded when it was written"
        )
    grid = survey.read_depth_grid(subset_path)
    extent = survey.lonlat_extent(grid)
    box = extent["covered_bbox_lonlat"] or extent["grid_bbox_lonlat"]
    centre = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
    source = _source(
        request, product, manifest["response_sha256"], manifest["retrieved_utc"]
    )
    reference, vertical = survey.stated_vertical(
        grid.window,
        stated_datum=product["stated_vertical_datum"],
        basis=product["vertical_statement_basis"],
        at_lonlat=centre,
    )
    vertical["values_are"] = (
        "elevations, positive up: the seabed is stored as negative numbers below "
        "the datum"
    )
    finite = grid.window.values[np.isfinite(grid.window.values)]
    vertical["cells_at_or_above_datum"] = int((finite >= 0).sum())
    vertical["product_crs_name"] = facts["facts"].get("compound_crs_name")
    vertical["sign_note"] = (
        "the product's coordinate system is named as a depth; its stored values "
        "are elevations. The values are used as stored and are not re-signed."
    )
    vertical["converted_to_another_datum"] = False
    result = survey.process_seabed(
        grid, source, vertical_reference=reference, parameters=run["parameters"]
    )
    body: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "survey_version": survey.SURVEY_VERSION,
        "run_id": run["run_id"],
        "registry": run["registry"].value,
        "target_feature": None,
        "target_feature_note": (
            "none: no off-shore record holds a position, so the run is centred on "
            "nothing and attaches nothing"
        ),
        "evaluation_state": EvaluationState.EXPLORATORY.value,
        "products": [
            {
                "epoch": str(product.get("survey_date") or "unstated"),
                "source": source.to_dict(),
                "catalogue": request.to_dict(),
                "download": {
                    "size_bytes": manifest["response_size"],
                    "sha256": manifest["response_sha256"],
                    "retrieved_utc": manifest["retrieved_utc"],
                    "headers": manifest["headers"],
                },
                "subset": {
                    "file": SUBSET_NAME,
                    "sha256": subset_sha256,
                    "parent_sha256": manifest["response_sha256"],
                    "derivation": (
                        "the product's whole base grid, both bands, written losslessly"
                    ),
                },
                "product_facts": facts["facts"],
                "product_facts_basis": facts["read_from"],
                "layers_read": facts["layers_read"],
                "vertical": vertical,
                "vertical_uncertainty": {
                    "value_m": None,
                    "per_cell": True,
                    "basis": product["vertical_uncertainty_basis"],
                },
                "result": result.report,
                "search_area": search_area_relation(root, run, extent),
                "prior_receipt": prior_receipt_check(
                    root, product, manifest, result.report["surface"]
                ),
                "dry_registration": survey.dry_registration(
                    result,
                    source,
                    created_utc=str(manifest["retrieved_utc"]),
                    namespace=run["registry"],
                ),
            }
        ],
        "replication": None,
        "registry_changes": 0,
        "limits": [
            "a detection is a closed depression in a gridded seabed surface: a shape, not an opening, a passage or an identity",
            "a gridded bathymetric surface is a derived product; evidence from it cannot rise above SUPPORTING",
            "only the product's base grid was read; where it carries finer refinement grids they were not read, and a feature narrower than about two base cells cannot be seen",
            "a depression that nowhere exceeds the uncertainty of its own cells is not reported at all; one that exceeds it by less than the significance floor stays a candidate",
            "where the product's uncertainty is large, the absence of a detection is not the absence of a depression; the report says how much of the survey that is",
            "a reported area is the part of a depression above its cells' uncertainty, so it is a lower bound",
            "a depression cut by the edge of coverage is not closed inside the survey and is not reported",
            "depth and area thresholds are working values and are not calibrated against field truth",
            "one survey of one epoch: nothing here is replicated, seen by a second sensor or checked in the field",
            "depths are relative to the tidal datum the product states; nothing was converted to another datum or joined to a land surface",
            "the search area is an analyst-drawn box; a survey lying inside it places no seed and no feature",
            "no feature, observation or status in a committed registry was changed by this run",
        ],
    }
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    return body


def write_report(
    report: Mapping[str, Any], *, repo_root: str | Path, set_current: bool = True
) -> str:
    root = Path(repo_root) / SURVEY_DIR
    digest = _write_json(root / str(report["run_id"]) / REPORT_NAME, report)
    if set_current:
        _write_json(
            root / POINTER_NAME,
            {
                "schema": POINTER_SCHEMA,
                "run_id": report["run_id"],
                "report": f"{report['run_id']}/{REPORT_NAME}",
                "report_sha256": digest,
            },
        )
    return digest


def current_report(repo_root: str | Path) -> dict[str, Any] | None:
    """The seabed report the pointer names, checked against the pointer's hash."""

    root = Path(repo_root) / SURVEY_DIR
    pointer_path = root / POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer.get("schema") != POINTER_SCHEMA:
        raise SeabedRunError(f"{pointer_path} is not a seabed pointer")
    relative = Path(str(pointer["report"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise SeabedRunError("pointer must name a path inside the survey folder")
    path = root / relative
    if not path.is_file():
        raise SeabedRunError(f"pointer names a missing report: {relative}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer["report_sha256"]:
        raise SeabedRunError(f"{relative} does not match the pointer's hash")
    return _sealed(path, REPORT_SCHEMA)


def check_report(run: Mapping[str, Any], *, repo_root: str | Path) -> list[str]:
    """Problems found when the committed report is recomputed from evidence."""

    root = Path(repo_root)
    path = _run_dir(root, run) / REPORT_NAME
    if not path.is_file():
        return ["no report is committed for this run"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    try:
        rebuilt = build_report(run, repo_root=root)
    except (SeabedRunError, survey.SurveyReadError, ValueError, LookupError) as exc:
        return [f"{type(exc).__name__}: {exc}"]
    if rebuilt == committed:
        return []
    differing = sorted(
        key
        for key in set(rebuilt) | set(committed)
        if rebuilt.get(key) != committed.get(key)
    )
    return [f"the committed report is not reproduced; differing fields: {differing}"]
