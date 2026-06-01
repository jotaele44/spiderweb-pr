#!/usr/bin/env python3
"""Route reviewed PR DEM candidate GeoJSON into decision queues.

Input
-----
- reviewed_candidates.geojson from tools/pr_dem_review_lock.py

Outputs
-------
- queue_retained.geojson / .csv
- queue_rejected.geojson / .csv
- queue_escalated.geojson / .csv
- queue_second_pass.geojson / .csv
- queue_insufficient_evidence.geojson / .csv
- queue_unreviewed.geojson / .csv
- queue_summary.json
- queue_summary.md
- queue_manifest.json

This router preserves original feature geometry/properties and only assigns queue
metadata. It does not convert reviewed candidates into confirmed findings.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


QUEUE_ORDER = [
    "escalated",
    "retained",
    "second_pass",
    "insufficient_evidence",
    "rejected",
    "unreviewed",
]

QUEUE_FILES = {
    "escalated": "queue_escalated",
    "retained": "queue_retained",
    "second_pass": "queue_second_pass",
    "insufficient_evidence": "queue_insufficient_evidence",
    "rejected": "queue_rejected",
    "unreviewed": "queue_unreviewed",
}

REJECT_DECISIONS = {
    "reject_natural_feature",
    "reject_known_ordinary_infrastructure",
    "reject_data_artifact",
}

RETAIN_DECISIONS = {
    "retain_candidate",
    "retain_low_priority",
}

ESCALATE_DECISIONS = {
    "escalate_high_priority",
}

INSUFFICIENT_DECISIONS = {
    "insufficient_evidence",
}

SECOND_PASS_STATUS = {
    "needs_second_pass",
    "in_review",
}

CSV_FIELDS = [
    "candidate_id",
    "queue",
    "queue_reason",
    "ILAP_SCORE",
    "review_decision",
    "review_status",
    "review_confidence",
    "review_recommended_next_step",
    "review_terrain_visual_type",
    "review_access_context",
    "review_hydro_context",
    "review_utility_context",
    "review_karst_context",
    "review_imagery_context",
    "review_evidence_tier",
    "lon",
    "lat",
    "x",
    "y",
    "source_tile",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_geojson(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit(f"Input must be a FeatureCollection GeoJSON: {path}")
    if not isinstance(payload.get("features"), list):
        raise SystemExit(f"Input GeoJSON has no feature list: {path}")
    return payload


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def first_value(props: Dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = props.get(name)
        if value is not None and value != "":
            return value
    return None


def normalized_review_fields(props: Dict[str, Any]) -> Dict[str, Any]:
    """Support both original review CSV names and review-lock prefixed names."""
    return {
        "review_decision": first_value(props, ["review_review_decision", "review_decision"]),
        "review_status": first_value(props, ["review_review_status", "review_status"]),
        "review_confidence": first_value(props, ["review_review_confidence", "review_confidence"]),
        "recommended_next_step": first_value(props, ["review_recommended_next_step", "recommended_next_step"]),
        "terrain_visual_type": first_value(props, ["review_terrain_visual_type", "terrain_visual_type"]),
        "access_context": first_value(props, ["review_access_context", "access_context"]),
        "hydro_context": first_value(props, ["review_hydro_context", "hydro_context"]),
        "utility_context": first_value(props, ["review_utility_context", "utility_context"]),
        "karst_context": first_value(props, ["review_karst_context", "karst_context"]),
        "imagery_context": first_value(props, ["review_imagery_context", "imagery_context"]),
        "evidence_tier": first_value(props, ["review_evidence_tier", "evidence_tier"]),
    }


def route_feature(feature: Dict[str, Any]) -> Tuple[str, str]:
    props = feature.get("properties") or {}
    fields = normalized_review_fields(props)
    decision = fields.get("review_decision")
    status = fields.get("review_status")
    next_step = fields.get("recommended_next_step")

    if not decision and props.get("review_merge_status") == "no_review_row":
        return "unreviewed", "no_review_row"
    if decision in ESCALATE_DECISIONS:
        return "escalated", str(decision)
    if status in SECOND_PASS_STATUS or next_step == "second_reviewer":
        return "second_pass", f"status={status}; next_step={next_step}"
    if decision in INSUFFICIENT_DECISIONS:
        return "insufficient_evidence", str(decision)
    if decision in REJECT_DECISIONS:
        return "rejected", str(decision)
    if decision in RETAIN_DECISIONS:
        return "retained", str(decision)
    if not decision:
        return "unreviewed", "missing_review_decision"
    return "second_pass", f"unmapped_decision={decision}"


def routed_feature_copy(feature: Dict[str, Any], queue: str, reason: str) -> Dict[str, Any]:
    out = dict(feature)
    out["properties"] = dict(feature.get("properties") or {})
    out["properties"]["decision_queue"] = queue
    out["properties"]["decision_queue_reason"] = reason
    out["properties"]["decision_routed_at_utc"] = utc_now()
    return out


def route_geojson(payload: Dict[str, Any]) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    queues: Dict[str, List[Dict[str, Any]]] = {name: [] for name in QUEUE_ORDER}
    all_features: List[Dict[str, Any]] = []
    for feature in payload.get("features", []):
        queue, reason = route_feature(feature)
        out = routed_feature_copy(feature, queue, reason)
        queues[queue].append(out)
        all_features.append(out)
    return queues, all_features


def feature_collection(features: Sequence[Dict[str, Any]], name: str, source_path: Path) -> Dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": name,
        "generated_at_utc": utc_now(),
        "source_reviewed_geojson": str(source_path),
        "features": list(features),
        "guardrail": "Decision queues are review-management outputs only and do not confirm hidden infrastructure or subsurface activity.",
    }


def csv_row(feature: Dict[str, Any]) -> Dict[str, Any]:
    props = feature.get("properties") or {}
    fields = normalized_review_fields(props)
    return {
        "candidate_id": props.get("candidate_id", ""),
        "queue": props.get("decision_queue", ""),
        "queue_reason": props.get("decision_queue_reason", ""),
        "ILAP_SCORE": props.get("ILAP_SCORE", ""),
        "review_decision": fields.get("review_decision", ""),
        "review_status": fields.get("review_status", ""),
        "review_confidence": fields.get("review_confidence", ""),
        "review_recommended_next_step": fields.get("recommended_next_step", ""),
        "review_terrain_visual_type": fields.get("terrain_visual_type", ""),
        "review_access_context": fields.get("access_context", ""),
        "review_hydro_context": fields.get("hydro_context", ""),
        "review_utility_context": fields.get("utility_context", ""),
        "review_karst_context": fields.get("karst_context", ""),
        "review_imagery_context": fields.get("imagery_context", ""),
        "review_evidence_tier": fields.get("evidence_tier", ""),
        "lon": props.get("lon", props.get("review_lon", "")),
        "lat": props.get("lat", props.get("review_lat", "")),
        "x": props.get("x", props.get("review_x", "")),
        "y": props.get("y", props.get("review_y", "")),
        "source_tile": props.get("source_tile", props.get("review_source_tile", "")),
    }


def write_queue_csv(path: Path, features: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for feature in features:
            writer.writerow(csv_row(feature))


def write_outputs(queues: Dict[str, List[Dict[str, Any]]], source_path: Path, output_dir: Path) -> List[Path]:
    written: List[Path] = []
    for queue in QUEUE_ORDER:
        base = QUEUE_FILES[queue]
        geojson_path = output_dir / f"{base}.geojson"
        csv_path = output_dir / f"{base}.csv"
        write_json(geojson_path, feature_collection(queues[queue], base, source_path))
        write_queue_csv(csv_path, queues[queue])
        written.extend([geojson_path, csv_path])
    return written


def summarize_queues(queues: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    decision_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    next_step_counts: Counter[str] = Counter()
    score_by_queue: Dict[str, Dict[str, Any]] = {}

    for queue, features in queues.items():
        scores: List[float] = []
        for feature in features:
            props = feature.get("properties") or {}
            fields = normalized_review_fields(props)
            if fields.get("review_decision"):
                decision_counts[str(fields["review_decision"])] += 1
            if fields.get("review_status"):
                status_counts[str(fields["review_status"])] += 1
            if fields.get("review_confidence"):
                confidence_counts[str(fields["review_confidence"])] += 1
            if fields.get("recommended_next_step"):
                next_step_counts[str(fields["recommended_next_step"])] += 1
            try:
                scores.append(float(props.get("ILAP_SCORE")))
            except Exception:
                pass
        score_by_queue[queue] = {
            "count": len(scores),
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "mean": round(sum(scores) / len(scores), 3) if scores else None,
        }

    return {
        "generated_at_utc": utc_now(),
        "queue_counts": {queue: len(queues[queue]) for queue in QUEUE_ORDER},
        "decision_counts": dict(decision_counts),
        "status_counts": dict(status_counts),
        "confidence_counts": dict(confidence_counts),
        "recommended_next_step_counts": dict(next_step_counts),
        "score_by_queue": score_by_queue,
        "guardrail": "Queues are review-management categories only. They do not establish confirmed infrastructure or subsurface activity.",
    }


def write_summary_md(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# PR DEM Review Decision Queue Summary")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_at_utc']}`")
    lines.append("")
    lines.append("## Queue counts")
    lines.append("")
    lines.append("| Queue | Count |")
    lines.append("|---|---:|")
    for queue in QUEUE_ORDER:
        lines.append(f"| {queue} | {summary['queue_counts'].get(queue, 0)} |")
    lines.append("")
    lines.append("## Score by queue")
    lines.append("")
    lines.append("| Queue | Count | Min | Max | Mean |")
    lines.append("|---|---:|---:|---:|---:|")
    for queue in QUEUE_ORDER:
        s = summary["score_by_queue"].get(queue, {})
        lines.append(f"| {queue} | {s.get('count')} | {s.get('min')} | {s.get('max')} | {s.get('mean')} |")
    lines.append("")
    for title, key in [
        ("Review decision counts", "decision_counts"),
        ("Review status counts", "status_counts"),
        ("Review confidence counts", "confidence_counts"),
        ("Recommended next-step counts", "recommended_next_step_counts"),
    ]:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Value | Count |")
        lines.append("|---|---:|")
        counts = summary.get(key, {})
        if counts:
            for value, count in sorted(counts.items()):
                lines.append(f"| {value} | {count} |")
        else:
            lines.append("| none | 0 |")
        lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append(summary["guardrail"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, input_path: Path, output_paths: Sequence[Path], summary: Dict[str, Any]) -> None:
    payload = {
        "generated_at_utc": utc_now(),
        "tool": "tools/pr_dem_review_decision_router.py",
        "input": {
            "path": str(input_path),
            "size_bytes": input_path.stat().st_size,
            "sha256": sha256_file(input_path),
        },
        "queue_counts": summary["queue_counts"],
        "outputs": [
            {
                "path": str(path),
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in output_paths
            if path.exists()
        ],
        "guardrail": summary["guardrail"],
    }
    write_json(path, payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Split reviewed PR DEM candidate GeoJSON into decision queues.")
    p.add_argument("--reviewed-geojson", required=True, help="reviewed_candidates.geojson from pr_dem_review_lock.py")
    p.add_argument("--output-dir", default="outputs/pr_dem_review_queues", help="Output directory for queue files.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    reviewed_path = Path(args.reviewed_geojson).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not reviewed_path.exists() or reviewed_path.stat().st_size == 0:
        raise SystemExit(f"Missing or empty reviewed GeoJSON: {reviewed_path}")

    payload = load_geojson(reviewed_path)
    queues, all_features = route_geojson(payload)
    output_paths = write_outputs(queues, reviewed_path, output_dir)

    all_path = output_dir / "queue_all_routed.geojson"
    write_json(all_path, feature_collection(all_features, "queue_all_routed", reviewed_path))
    output_paths.append(all_path)

    summary = summarize_queues(queues)
    summary_json = output_dir / "queue_summary.json"
    summary_md = output_dir / "queue_summary.md"
    manifest_path = output_dir / "queue_manifest.json"
    write_json(summary_json, summary)
    write_summary_md(summary_md, summary)
    output_paths.extend([summary_json, summary_md])
    write_manifest(manifest_path, reviewed_path, output_paths, summary)

    print("Decision routing complete")
    print(f"Output dir: {output_dir}")
    for queue in QUEUE_ORDER:
        print(f"{queue}: {len(queues[queue])}")
    print(f"Summary: {summary_md}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
