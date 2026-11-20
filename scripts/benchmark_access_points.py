#!/usr/bin/env python3
"""Measure the access-point processing core and query service.

Everything reported is measured in the run that produced it, on synthetic
control surfaces of stated size.  Nothing is extrapolated.  The numbers describe
software performance on this machine; they say nothing about detection accuracy.

    python scripts/benchmark_access_points.py --output evidence/access_points/benchmark_v1.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from gebco.marine_evidence import (  # noqa: E402
    CoverageState,
    ProductStage,
    SensorType,
    VerticalReference,
)
from spiderweb.access_points import controls, detection, raster  # noqa: E402
from spiderweb.access_points.models import (  # noqa: E402
    HORIZONTAL_INTERCHANGE_CRS,
    EvidenceAssertion,
    Observation,
    SourceManifestation,
)
from spiderweb.access_points.namespaces import (  # noqa: E402
    Namespace,
    observation_id,
    source_id,
)
from spiderweb.access_points.registry import AccessPointRegistry  # noqa: E402
from spiderweb.access_points.seeding import build_all, write_documents  # noqa: E402
from spiderweb.access_points.service import AccessPointService  # noqa: E402
from spiderweb.access_points.vocabulary import (  # noqa: E402
    ClaimClass,
    EvidenceDimension,
    EvidenceTier,
    GeometryBasis,
    ProvenanceState,
)

BENCHMARK_SCHEMA = "access_point_benchmark/1.0"


def measure(fn: Callable[[], Any], *, repeats: int = 3) -> dict[str, Any]:
    """Wall time (best and median of ``repeats``) and peak traced memory."""

    times = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - start)
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "best_s": round(min(times), 4),
        "median_s": round(statistics.median(times), 4),
        "peak_traced_mb": round(peak / 1e6, 2),
        "repeats": repeats,
        "_result": result,
    }


def _strip(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "_result"}


def _land(n: int) -> raster.SurfaceGrid:
    rng = np.random.default_rng(5)
    surface = controls.tilted_plane(n, n, base_m=150.0, slope_x=0.01, slope_y=0.006)
    step = max(n // 12, 40)
    for r in range(step, n - step, step):
        for c in range(step, n - step, step):
            surface = (
                controls.add_gaussian_basin(
                    surface,
                    float(r),
                    float(c),
                    depth_m=float(rng.uniform(2, 9)),
                    sigma_cells=float(rng.uniform(5, 11)),
                )
                if n <= 1024
                else surface
            )
    if n > 1024:
        # Large grids: stamp basins into windows instead of full-grid Gaussians.
        yy, xx = np.mgrid[-40:41, -40:41].astype(np.float64)
        for r in range(step, n - step, step):
            for c in range(step, n - step, step):
                bowl = np.exp(-((xx**2 + yy**2) / (2.0 * rng.uniform(5, 11) ** 2)))
                surface[r - 40 : r + 41, c - 40 : c + 41] -= rng.uniform(2, 9) * bowl
    surface = controls.add_noise(surface, sigma_m=0.03, seed=9)
    return raster.make_grid(
        surface,
        cell_size_m=(1.0, 1.0),
        origin=(200000.0, 2000000.0 + n),
        crs="EPSG:32619",
        kind=raster.SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=VerticalReference(
            "EPSG:32619", "EPSG:6641", None, None, "up"
        ),
        uncertainty_m=0.1,
        expect="emergent",
    )


def _source(root: str) -> SourceManifestation:
    return SourceManifestation(
        source_id=source_id("BENCHMARK", root, None, "e" * 64),
        provider="BENCHMARK",
        title="synthetic control surface",
        native_identifier=root,
        manifestation_sha256="e" * 64,
        retrieved_utc="2026-11-15T00:00:00Z",
        lineage_root_id=root,
        product_stage=ProductStage.PROCESSED_OBSERVATION,
        sensor_type=SensorType.TOPOBATHYMETRIC_LIDAR,
        coverage_state=CoverageState.DIRECTLY_OBSERVED,
        provenance_state=ProvenanceState.REGISTERED,
    )


def bench_processing(sizes: list[int]) -> list[dict[str, Any]]:
    rows = []
    params = detection.DetectionParameters(min_depth_m=1.0, min_area_m2=40.0)
    source = _source("bench-lidar")
    for n in sizes:
        grid = _land(n)
        cells = n * n
        fill = measure(lambda: raster.fill_depressions(grid))
        regions = measure(
            lambda: raster.delineate_depressions(
                grid, min_depth_m=1.0, min_area_m2=40.0
            )
        )
        detect = measure(lambda: detection.detect_inland(grid, source, params))
        nested = measure(
            lambda: raster.delineate_depressions(
                grid, min_depth_m=1.0, min_area_m2=40.0, nested=True
            )
        )
        seams = measure(lambda: raster.detect_seams(grid))
        slope = measure(lambda: raster.slope_degrees(grid))
        rows.append(
            {
                "cells": cells,
                "shape": [n, n],
                "input_mb": round(grid.values.nbytes / 1e6, 2),
                "fill_depressions": _strip(fill),
                "delineate_depressions": {
                    **_strip(regions),
                    "regions_found": len(regions["_result"]),
                    "cells_per_second": round(cells / regions["best_s"]),
                },
                "detect_inland": {
                    **_strip(detect),
                    "detections": len(detect["_result"]),
                },
                # Opt-in: the default path above does not run this.
                "delineate_depressions_nested": {
                    **_strip(nested),
                    "regions_found": len(nested["_result"]),
                    "nested_regions": sum(
                        1 for r in nested["_result"] if r.hierarchy_level > 0
                    ),
                },
                "detect_seams": _strip(seams),
                "slope_degrees": _strip(slope),
            }
        )
    return rows


def bench_tiling(n: int) -> dict[str, Any]:
    grid = _land(n)
    radius = 8
    whole = measure(lambda: raster.position_index(grid, radius), repeats=2)
    tiled = measure(
        lambda: raster.apply_tiled(
            grid,
            lambda sub: raster.position_index(sub, radius),
            tile=512,
            halo=radius + 1,
        ),
        repeats=2,
    )
    identical = bool(np.allclose(whole["_result"], tiled["_result"], equal_nan=True))
    return {
        "operation": f"position_index(radius={radius} cells)",
        "shape": [n, n],
        "untiled": _strip(whole),
        "tiled_512_halo_9": _strip(tiled),
        "results_identical": identical,
        "peak_memory_ratio_tiled_over_untiled": round(
            tiled["peak_traced_mb"] / whole["peak_traced_mb"], 3
        ),
    }


def _synthetic_registry(count: int) -> AccessPointRegistry:
    registry = AccessPointRegistry(
        Namespace.ACCESS_POINT_INLAND, producer_identity="benchmark"
    )
    source = _source("bench-registry")
    registry.add_source(source)
    rng = np.random.default_rng(3)
    lons = rng.uniform(-67.3, -65.2, count)
    lats = rng.uniform(17.9, 18.5, count)
    for i in range(count):
        observation = Observation(
            observation_id=observation_id(
                registry.namespace, source.source_id, f"cell-{i}"
            ),
            namespace=registry.namespace,
            source_id=source.source_id,
            native_record_id=f"cell-{i}",
            geometry_basis=GeometryBasis.DERIVED_FROM_RASTER,
            geometry={"type": "Point", "coordinates": [float(lons[i]), float(lats[i])]},
            horizontal_crs=HORIZONTAL_INTERCHANGE_CRS,
            horizontal_uncertainty_m=2.0,
            claim_class=ClaimClass.COMPUTED,
        )
        registry.add_observation(observation)
        registry.register_candidate(
            "CLOSED_DEPRESSION",
            observation_ids=(observation.observation_id,),
            assertions=(
                EvidenceAssertion(
                    dimension=EvidenceDimension.EXISTENCE,
                    tier=EvidenceTier.SUPPORTING,
                    claim_class=ClaimClass.COMPUTED,
                    basis=("terrain_derivative",),
                    statement="synthetic benchmark record",
                    source_ids=(source.source_id,),
                    method="benchmark",
                    method_version="1",
                ),
            ),
        )
    return registry


def bench_service(count: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        build = measure(lambda: build_all(REPO_ROOT), repeats=3)
        write_documents(build["_result"], root)
        registry_dir = root / "registry" / "access_points"
        ingest = measure(lambda: _synthetic_registry(count), repeats=1)
        registry = ingest["_result"]
        save = measure(lambda: registry.save(registry_dir / "inland.json"), repeats=2)
        size_mb = (registry_dir / "inland.json").stat().st_size / 1e6
        load = measure(
            lambda: AccessPointRegistry.load(registry_dir / "inland.json"), repeats=2
        )

        service = AccessPointService(root)
        service.feature_collection(
            "inland", limit=1
        )  # warm: verified once, then cached
        samples: dict[str, list[float]] = {
            "page_100": [],
            "bbox_100": [],
            "evidence": [],
        }
        first = service.feature_collection("inland", limit=1)["features"][0]["id"]
        for _ in range(30):
            t = time.perf_counter()
            service.feature_collection("inland", limit=100)
            samples["page_100"].append(time.perf_counter() - t)
            t = time.perf_counter()
            service.feature_collection(
                "inland", bbox=(-66.6, 18.1, -66.2, 18.3), limit=100
            )
            samples["bbox_100"].append(time.perf_counter() - t)
            t = time.perf_counter()
            service.evidence("inland", first)
            samples["evidence"].append(time.perf_counter() - t)

        def latency(values: list[float]) -> dict[str, float]:
            ordered = sorted(values)
            return {
                "median_ms": round(statistics.median(ordered) * 1000, 2),
                "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))] * 1000, 2),
                "samples": len(ordered),
            }

        return {
            "committed_registry_build": _strip(build),
            "synthetic_registry_features": count,
            "ingest_with_rule_checks": {
                **_strip(ingest),
                "features_per_second": round(count / ingest["best_s"]),
            },
            "document_size_mb": round(size_mb, 2),
            "save_document": _strip(save),
            "load_and_verify_document": _strip(load),
            "query_latency_in_process": {
                name: latency(v) for name, v in samples.items()
            },
            "note": (
                "in-process service calls; HTTP serialisation and network are not included. "
                "Queries scan all features: no spatial index is used at this size."
            ),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[512, 1024, 2048])
    parser.add_argument("--tiling-size", type=int, default=2048)
    parser.add_argument("--registry-features", type=int, default=5000)
    parser.add_argument("--generated-utc", default=None)
    args = parser.parse_args(argv)

    import scipy
    import skimage

    report = {
        "schema": BENCHMARK_SCHEMA,
        "generated_utc": args.generated_utc
        or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim_class": "COMPUTED",
        "statement": (
            "Measured on synthetic control surfaces in the run that wrote this file. "
            "Software performance only; not detection accuracy. There is no earlier "
            "implementation of closed-basin delineation in this repository to compare against."
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor_count": __import__("os").cpu_count(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "scikit_image": skimage.__version__,
        },
        "processing": bench_processing(args.sizes),
        "tiling": bench_tiling(args.tiling_size),
        "registry_and_service": bench_service(args.registry_features),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
