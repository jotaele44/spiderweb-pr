"""A declared, reproducible run of real-survey processing.

A run is described in ``configs/access_point_survey_runs.yaml`` and has two
halves, kept apart on purpose:

* :func:`extract` needs the held products (hundreds of megabytes, never
  committed).  It verifies each against its download manifest, cuts the
  window, and writes the small pieces that *are* committed: the lossless
  window subsets, copies of the download manifests, and a compact summary of
  a wider window.
* :func:`build_report` needs only what is committed.  It re-reads the frozen
  catalogue answer, checks every subset against its recorded hash, processes
  the subsets and writes one sealed report.  Anyone with the repository can
  re-run it and must get the same report.

The window centre is the point a registry already holds for the target
record.  The run reads it from the registry document; it is never typed into
the configuration, and the run changes no record.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

import yaml

from federation.spatial_core import canonical_json_sha256
from pipeline.marine_sources import BoundingBox

from . import CONTRACT_VERSION, survey
from .acquisition import replay_transport
from .detection import DetectionParameters
from .discovery import registered_points
from .namespaces import REGISTRY_NAMESPACES, Namespace
from .products import (
    MANIFEST_SCHEMA,
    TNM_PROVIDER,
    ProductRequest,
    held_product,
    tnm_elevation_products,
)
from .registry import AccessPointRegistry

RUNS_VERSION = "access_point_survey_runs_v1"
RUNS_PATH = "configs/access_point_survey_runs.yaml"
SURVEY_DIR = "evidence/access_points/real_survey"
POINTER_NAME = "CURRENT.json"
POINTER_SCHEMA = "access_point_survey_pointer/1.0"
REPORT_NAME = "processing_report.json"
REPORT_SCHEMA = "access_point_survey_report/1.0"
WIDE_NAME = "wide_window.json"
CATALOGUE_HALF_WIDTH_DEG = 0.005
REGISTRY_FILES = {
    Namespace.ACCESS_POINT_INLAND: "registry/access_points/inland.json",
    Namespace.ACCESS_POINT_OFFSHORE: "registry/access_points/offshore.json",
}


class SurveyRunError(ValueError):
    """The run configuration or its committed evidence is not usable."""


def load_run(config_path: str | Path, run_id: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("version") != RUNS_VERSION:
        raise SurveyRunError(f"{config_path}: unsupported survey-run file")
    for run in data.get("runs") or []:
        if str(run.get("run_id")) == run_id:
            return _validated(dict(run))
    raise SurveyRunError(f"no survey run {run_id!r} is declared")


def _validated(run: dict[str, Any]) -> dict[str, Any]:
    forbidden = sorted(
        set(run) & {"center", "centre", "lon", "lat", "coordinates", "geometry"}
    )
    if forbidden:
        raise SurveyRunError(
            f"a run may not state a position ({forbidden}); the centre is read "
            "from the registry"
        )
    try:
        namespace = Namespace(run["registry"])
    except (KeyError, ValueError) as exc:
        raise SurveyRunError("a run must name a registry") from exc
    if namespace not in REGISTRY_NAMESPACES:
        raise SurveyRunError(f"{namespace.value} is not a registry")
    run["registry"] = namespace
    if not str(run.get("target_feature") or "").strip():
        raise SurveyRunError("a run must name the record its window is centred on")
    for key in ("half_size_m", "wide_half_size_m", "wide_deep_threshold_m"):
        if not isinstance(run.get(key), (int, float)) or run[key] <= 0:
            raise SurveyRunError(f"{key} must be a positive number")
    parameters = run.get("parameters") or {}
    if "nested" not in parameters:
        raise SurveyRunError(
            "a run must say whether nested basins are reported (parameters.nested)"
        )
    run["parameters"] = DetectionParameters(
        min_depth_m=float(parameters["min_depth_m"]),
        min_area_m2=float(parameters["min_area_m2"]),
        nested=bool(parameters["nested"]),
    )
    products = run.get("products")
    if not isinstance(products, list) or not products:
        raise SurveyRunError("a run must list at least one product")
    epochs = [str(p.get("epoch")) for p in products]
    if len(epochs) != len(set(epochs)):
        raise SurveyRunError("product epochs must be unique")
    for product in products:
        for key in ("filename", "native_identifier", "stated_vertical_datum"):
            if not str(product.get(key) or "").strip():
                raise SurveyRunError(
                    f"product {product.get('epoch')}: {key} is required"
                )
        for key in ("vertical_statement_basis", "vertical_uncertainty_basis"):
            text = " ".join(str(product.get(key) or "").split())
            if not text:
                raise SurveyRunError(
                    f"product {product.get('epoch')}: {key} must say where the value "
                    "was read, or that none is published"
                )
            product[key] = text
        uncertainty = product.get("vertical_uncertainty_m")
        if uncertainty is not None and (
            not isinstance(uncertainty, (int, float)) or uncertainty <= 0
        ):
            raise SurveyRunError("vertical_uncertainty_m must be positive or null")
    return run


def target_point(repo_root: Path, run: Mapping[str, Any]) -> tuple[float, float]:
    registry = AccessPointRegistry.load(repo_root / REGISTRY_FILES[run["registry"]])
    points = registered_points(registry)
    try:
        return points[run["target_feature"]]
    except KeyError:
        raise SurveyRunError(
            f"{run['target_feature']} holds no registered point; a window cannot "
            "be centred on a record without one"
        ) from None


def _run_dir(repo_root: Path, run: Mapping[str, Any]) -> Path:
    return repo_root / SURVEY_DIR / str(run["run_id"])


def _catalogue(repo_root: Path, run: Mapping[str, Any]) -> dict[str, ProductRequest]:
    """The frozen catalogue answer, replayed offline, keyed by file name."""

    lon, lat = target_point(repo_root, run)
    half = CATALOGUE_HALF_WIDTH_DEG
    box = BoundingBox(
        round(lon - half, 6),
        round(lat - half, 6),
        round(lon + half, 6),
        round(lat + half, 6),
    )
    _, listed = tnm_elevation_products(
        box, transport=replay_transport(_run_dir(repo_root, run) / "catalogue")
    )
    return {product.filename: product for product in listed}


def _subset_name(epoch: str) -> str:
    return f"window_{epoch}.tif"


def extract(
    run: Mapping[str, Any], *, repo_root: str | Path, product_dir: str | Path
) -> dict[str, Any]:
    """Cut the committed pieces out of the held products.  No network."""

    root = Path(repo_root)
    run_dir = _run_dir(root, run)
    listed = _catalogue(root, run)
    point = target_point(root, run)
    wide: dict[str, Any] = {}
    written: dict[str, str] = {}
    for product in run["products"]:
        request = listed.get(product["filename"])
        if request is None or request.native_identifier != product["native_identifier"]:
            raise SurveyRunError(
                f"{product['filename']} is not in the frozen catalogue answer"
            )
        held = held_product(request, product_dir)
        if held is None:
            raise SurveyRunError(f"{product['filename']} is not held in {product_dir}")
        (run_dir / "products").mkdir(parents=True, exist_ok=True)
        shutil.copy(
            Path(product_dir) / (product["filename"] + ".manifest.json"),
            run_dir / "products" / (product["filename"] + ".manifest.json"),
        )
        window = survey.read_window(
            held.path, center_lonlat=point, half_size_m=float(run["half_size_m"])
        )
        written[product["epoch"]] = survey.write_subset(
            window, run_dir / "subsets" / _subset_name(product["epoch"])
        )
        source = _source(request, product, held.sha256, held.retrieved_utc)
        reference, _ = survey.stated_vertical(
            window,
            stated_datum=product["stated_vertical_datum"],
            basis=product["vertical_statement_basis"],
            at_lonlat=point,
        )
        big = survey.read_window(
            held.path, center_lonlat=point, half_size_m=float(run["wide_half_size_m"])
        )
        result = survey.process_terrain(
            big,
            source,
            vertical_reference=reference,
            uncertainty_m=product.get("vertical_uncertainty_m"),
            parameters=run["parameters"],
        )
        wide[product["epoch"]] = {
            "parent_sha256": held.sha256,
            **survey.wide_summary(
                result, lonlat=point, deep_m=float(run["wide_deep_threshold_m"])
            ),
        }
    body = {
        "schema": "access_point_survey_wide_window/1.0",
        "run_id": run["run_id"],
        "half_size_m": run["wide_half_size_m"],
        "reproducible_from": "the held products named by parent_sha256; not from the repository alone",
        "epochs": wide,
    }
    body["content_sha256"] = canonical_json_sha256(body)
    _write_json(run_dir / WIDE_NAME, body)
    return {"subsets": written, "wide_window": body}


def _source(
    request: ProductRequest,
    product: Mapping[str, Any],
    sha256: str,
    retrieved_utc: str,
) -> Any:
    return survey.gridded_source(
        provider=TNM_PROVIDER,
        native_identifier=request.native_identifier,
        title=request.title,
        source_uri=request.url,
        sha256=sha256,
        retrieved_utc=retrieved_utc,
        published_date=request.published,
        survey_date=product.get("survey_date"),
        lineage_root_id=product.get("lineage_root_id") or request.native_identifier,
    )


def _product_manifest(run_dir: Path, filename: str) -> dict[str, Any]:
    path = run_dir / "products" / (filename + ".manifest.json")
    if not path.is_file():
        raise SurveyRunError(f"no download manifest is committed for {filename}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise SurveyRunError(f"{path.name} is not a product manifest")
    return manifest


def build_report(run: Mapping[str, Any], *, repo_root: str | Path) -> dict[str, Any]:
    """The sealed report, computed from committed evidence only."""

    root = Path(repo_root)
    run_dir = _run_dir(root, run)
    listed = _catalogue(root, run)
    point = target_point(root, run)
    products: list[dict[str, Any]] = []
    results: dict[str, survey.SurveyResult] = {}
    sources: dict[str, Any] = {}
    for product in run["products"]:
        epoch = product["epoch"]
        request = listed.get(product["filename"])
        if request is None or request.native_identifier != product["native_identifier"]:
            raise SurveyRunError(
                f"{product['filename']} is not in the frozen catalogue answer"
            )
        manifest = _product_manifest(run_dir, product["filename"])
        if manifest["request"]["url"] != request.url or (
            request.size_bytes is not None
            and manifest["response_size"] != request.size_bytes
        ):
            raise SurveyRunError(
                f"{product['filename']}: the download manifest disagrees with the catalogue"
            )
        subset_path = run_dir / "subsets" / _subset_name(epoch)
        if not subset_path.is_file():
            raise SurveyRunError(f"the window subset for {epoch} is missing")
        window = survey.read_raster(subset_path)
        source = _source(
            request, product, manifest["response_sha256"], manifest["retrieved_utc"]
        )
        reference, vertical = survey.stated_vertical(
            window,
            stated_datum=product["stated_vertical_datum"],
            basis=product["vertical_statement_basis"],
            at_lonlat=point,
        )
        result = survey.process_terrain(
            window,
            source,
            vertical_reference=reference,
            uncertainty_m=product.get("vertical_uncertainty_m"),
            parameters=run["parameters"],
        )
        results[epoch] = result
        sources[epoch] = source
        products.append(
            {
                "epoch": epoch,
                "source": source.to_dict(),
                "catalogue": request.to_dict(),
                "download": {
                    "size_bytes": manifest["response_size"],
                    "sha256": manifest["response_sha256"],
                    "retrieved_utc": manifest["retrieved_utc"],
                    "headers": manifest["headers"],
                },
                "subset": {
                    "file": f"subsets/{_subset_name(epoch)}",
                    "sha256": survey.sha256_file(subset_path),
                    "parent_sha256": manifest["response_sha256"],
                    "derivation": "square window of the product's own cells, written losslessly",
                },
                "vertical": vertical,
                "vertical_uncertainty": {
                    "value_m": product.get("vertical_uncertainty_m"),
                    "basis": product["vertical_uncertainty_basis"],
                },
                "result": result.report,
                "relation_to_target": survey.nearest_detections(result, lonlat=point),
                "dry_registration": survey.dry_registration(
                    result, source, created_utc=str(manifest["retrieved_utc"])
                ),
            }
        )

    epochs = [p["epoch"] for p in run["products"]]
    replication = None
    if len(epochs) >= 2:
        replication = {
            "earlier": epochs[0],
            "later": epochs[1],
            **survey.compare_surveys(results[epochs[0]], results[epochs[1]]),
        }
    wide_path = run_dir / WIDE_NAME
    wide = (
        json.loads(wide_path.read_text(encoding="utf-8"))
        if wide_path.is_file()
        else None
    )
    if wide is not None:
        sealed = dict(wide)
        stated = sealed.pop("content_sha256", None)
        if canonical_json_sha256(sealed) != stated:
            raise SurveyRunError("the wide-window summary does not match its hash")
    body: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "survey_version": survey.SURVEY_VERSION,
        "run_id": run["run_id"],
        "registry": run["registry"].value,
        "target_feature": run["target_feature"],
        "target_point_lonlat": [point[0], point[1]],
        "target_point_basis": "read from the committed registry document; not typed into the run",
        "window_half_size_m": run["half_size_m"],
        "products": products,
        "replication": replication,
        "wide_window": wide,
        "registry_changes": 0,
        "limits": [
            "a detection is a closed basin in a gridded surface: a shape, not an opening, a passage or an identity",
            "a gridded elevation model is a derived product; evidence from it cannot rise above SUPPORTING",
            "a basin cut by the window edge is not closed inside the window and is not reported",
            "depth and area thresholds are working values and are not calibrated against field truth",
            "distance from a registered point to a basin is discovery; it attaches nothing to the record",
            "the stated vertical datum is recorded as stated; where it is regionally implausible the surface is not joined to another reference",
            "no feature, observation or status in a committed registry was changed by this run",
        ],
    }
    # Normalise to plain JSON types so a rebuilt report compares equal to a
    # committed one (tuples and lists are the same thing once written).
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    return body


def _write_json(path: Path, document: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    """The report the pointer names, checked against the pointer's hash."""

    root = Path(repo_root) / SURVEY_DIR
    pointer_path = root / POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer.get("schema") != POINTER_SCHEMA:
        raise SurveyRunError(f"{pointer_path} is not a survey pointer")
    relative = Path(str(pointer["report"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise SurveyRunError("pointer must name a path inside the survey folder")
    path = root / relative
    if not path.is_file():
        raise SurveyRunError(f"pointer names a missing report: {relative}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer["report_sha256"]:
        raise SurveyRunError(f"{relative} does not match the pointer's hash")
    report = json.loads(path.read_text(encoding="utf-8"))
    sealed = dict(report)
    stated = sealed.pop("content_sha256", None)
    if report.get("schema") != REPORT_SCHEMA or canonical_json_sha256(sealed) != stated:
        raise SurveyRunError(f"{relative} does not match its content hash")
    return report


def check_report(run: Mapping[str, Any], *, repo_root: str | Path) -> list[str]:
    """Problems found when the committed report is recomputed from evidence."""

    root = Path(repo_root)
    path = _run_dir(root, run) / REPORT_NAME
    if not path.is_file():
        return ["no report is committed for this run"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    try:
        rebuilt = build_report(run, repo_root=root)
    except (SurveyRunError, survey.SurveyReadError, ValueError, LookupError) as exc:
        return [f"{type(exc).__name__}: {exc}"]
    if rebuilt == committed:
        return []
    differing = sorted(
        key
        for key in set(rebuilt) | set(committed)
        if rebuilt.get(key) != committed.get(key)
    )
    return [f"the committed report is not reproduced; differing fields: {differing}"]
