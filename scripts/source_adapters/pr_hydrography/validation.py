from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class GeometryAudit:
    source_valid: bool
    analysis_valid: bool
    source_geometry_type: str
    analysis_geometry_type: str
    source_mutated: bool
    repair_applied: bool
    hausdorff_distance: float
    source_area: float
    analysis_area: float


def detect_csv_header(payload: bytes, required_fields: Sequence[str], *, max_scan_lines: int = 25) -> tuple[int, list[str], list[str]]:
    """Detect a CSV header without assuming line zero."""
    text = payload.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    required = {field.strip() for field in required_fields}
    for index, line in enumerate(lines[:max_scan_lines]):
        try:
            fields = next(csv.reader([line]))
        except csv.Error:
            continue
        normalized = {field.strip() for field in fields}
        if required <= normalized:
            return index, lines[:index], fields
    raise RuntimeError(f"CSV header not found within first {max_scan_lines} lines; required={sorted(required)}")


def csv_dict_rows(payload: bytes, required_fields: Sequence[str]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    header_index, preamble, fields = detect_csv_header(payload, required_fields)
    text = payload.decode("utf-8-sig", errors="replace")
    data = "\n".join(text.splitlines()[header_index:])
    rows = list(csv.DictReader(io.StringIO(data)))
    missing = [field for field in required_fields if field not in fields]
    if missing:
        raise RuntimeError(f"required CSV fields missing after header detection: {missing}")
    return rows, {
        "header_line_index": header_index,
        "preamble_lines": preamble,
        "column_count": len(fields),
        "columns": fields,
    }


def analysis_geometry(source: Any) -> tuple[Any, dict[str, Any]]:
    """Return an analysis-only valid geometry plus an immutable-source audit."""
    try:
        from shapely import make_valid
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("shapely is required for geometry validation") from exc

    source_wkb = source.wkb
    source_valid = bool(source.is_valid)
    analysis = source if source_valid else make_valid(source)
    analysis_valid = bool(analysis.is_valid)
    if not analysis_valid:
        raise RuntimeError("analysis geometry remains invalid after make_valid")
    audit = GeometryAudit(
        source_valid=source_valid,
        analysis_valid=analysis_valid,
        source_geometry_type=source.geom_type,
        analysis_geometry_type=analysis.geom_type,
        source_mutated=source.wkb != source_wkb,
        repair_applied=not source_valid,
        hausdorff_distance=float(source.hausdorff_distance(analysis)),
        source_area=float(source.area),
        analysis_area=float(analysis.area),
    )
    if audit.source_mutated:
        raise RuntimeError("source geometry mutated during analysis repair")
    return analysis, asdict(audit)


def audit_geojson_geometry(geometry: dict[str, Any]) -> GeometryAudit:
    try:
        from shapely.geometry import shape
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("shapely is required for geometry validation") from exc
    _analysis, audit = analysis_geometry(shape(geometry))
    return GeometryAudit(**audit)


def classify_geometries(features: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for index, feature in enumerate(features):
        geometry = feature.get("geometry")
        if geometry is None:
            rows.append({"index": index, "state": "NULL_GEOMETRY"})
            continue
        audit = audit_geojson_geometry(geometry)
        state = "VALID_SOURCE_GEOMETRY" if audit.source_valid else "INVALID_SOURCE_ANALYSIS_REPAIRED"
        rows.append({"index": index, "state": state, **audit.__dict__})
    unclassified = [row for row in rows if not row.get("state")]
    if unclassified:
        raise RuntimeError(f"unclassified geometry rows: {len(unclassified)}")
    return {
        "rows": rows,
        "total": len(rows),
        "valid_source": sum(row["state"] == "VALID_SOURCE_GEOMETRY" for row in rows),
        "invalid_source_repaired": sum(row["state"] == "INVALID_SOURCE_ANALYSIS_REPAIRED" for row in rows),
        "null_geometry": sum(row["state"] == "NULL_GEOMETRY" for row in rows),
        "unclassified": 0,
        "arithmetic_closure": len(rows) == sum(
            row["state"] in {"VALID_SOURCE_GEOMETRY", "INVALID_SOURCE_ANALYSIS_REPAIRED", "NULL_GEOMETRY"}
            for row in rows
        ),
    }
