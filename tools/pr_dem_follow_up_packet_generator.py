#!/usr/bin/env python3
"""Generate follow-up packets for reviewed PR DEM candidate queues.

Inputs
------
- queue_escalated.geojson and/or queue_retained.geojson from pr_dem_review_decision_router.py
- context checklist JSON from configs/pr_dem_follow_up_context_layers.json

Outputs
-------
- per-candidate markdown briefs
- follow_up_index.csv
- follow_up_index.json
- follow_up_manifest.json
- follow_up_packet_summary.md

Packets are review-management artifacts. They do not confirm infrastructure,
hidden infrastructure, or subsurface activity.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_CONTEXT_CONFIG = Path("configs") / "pr_dem_follow_up_context_layers.json"
DEFAULT_QUEUE_DIR = Path("outputs") / "pr_dem_review_queues"
DEFAULT_OUTPUT_DIR = Path("outputs") / "pr_dem_follow_up_packets"
DEFAULT_QUEUE_FILES = ["queue_escalated.geojson", "queue_retained.geojson"]

INDEX_FIELDS = [
    "packet_id",
    "candidate_id",
    "queue",
    "priority_rank",
    "ILAP_SCORE",
    "review_decision",
    "review_confidence",
    "recommended_next_step",
    "lon",
    "lat",
    "x",
    "y",
    "source_tile",
    "brief_path",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def slugify(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    return text.strip("_") or "unknown"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def first_value(props: Dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = props.get(name)
        if value is not None and value != "":
            return value
    return None


def normalized_fields(props: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidate_id": props.get("candidate_id", ""),
        "queue": props.get("decision_queue", ""),
        "queue_reason": props.get("decision_queue_reason", ""),
        "ILAP_SCORE": props.get("ILAP_SCORE", ""),
        "review_status": first_value(props, ["review_review_status", "review_status"]),
        "review_decision": first_value(props, ["review_review_decision", "review_decision"]),
        "review_confidence": first_value(props, ["review_review_confidence", "review_confidence"]),
        "recommended_next_step": first_value(props, ["review_recommended_next_step", "recommended_next_step"]),
        "terrain_visual_type": first_value(props, ["review_terrain_visual_type", "terrain_visual_type"]),
        "access_context": first_value(props, ["review_access_context", "access_context"]),
        "hydro_context": first_value(props, ["review_hydro_context", "hydro_context"]),
        "utility_context": first_value(props, ["review_utility_context", "utility_context"]),
        "karst_context": first_value(props, ["review_karst_context", "karst_context"]),
        "imagery_context": first_value(props, ["review_imagery_context", "imagery_context"]),
        "evidence_tier": first_value(props, ["review_evidence_tier", "evidence_tier"]),
        "review_notes": first_value(props, ["review_review_notes", "review_notes"]),
        "lon": first_value(props, ["lon", "review_lon"]),
        "lat": first_value(props, ["lat", "review_lat"]),
        "x": first_value(props, ["x", "review_x"]),
        "y": first_value(props, ["y", "review_y"]),
        "crs": first_value(props, ["crs", "review_crs"]),
        "source_tile": first_value(props, ["source_tile", "review_source_tile"]),
        "area_m2": first_value(props, ["area_m2", "review_area_m2"]),
        "mean_slope_deg": first_value(props, ["mean_slope_deg", "review_mean_slope_deg"]),
        "ring_mean_slope_deg": first_value(props, ["ring_mean_slope_deg", "review_ring_mean_slope_deg"]),
        "tpi_mean_m": first_value(props, ["tpi_mean_m", "review_tpi_mean_m"]),
    }


def score_value(fields: Dict[str, Any]) -> float:
    try:
        return float(fields.get("ILAP_SCORE"))
    except Exception:
        return -1.0


def load_queue_geojson(path: Path) -> List[Dict[str, Any]]:
    payload = load_json(path)
    if payload.get("type") != "FeatureCollection":
        raise SystemExit(f"Queue file is not a FeatureCollection: {path}")
    features = payload.get("features")
    if not isinstance(features, list):
        raise SystemExit(f"Queue file missing features list: {path}")
    rows: List[Dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        fields = normalized_fields(props)
        fields["source_queue_file"] = str(path)
        fields["geometry"] = feature.get("geometry")
        rows.append(fields)
    return rows


def discover_queue_files(queue_dir: Path, explicit_files: Sequence[str]) -> List[Path]:
    if explicit_files:
        return [Path(x).expanduser().resolve() for x in explicit_files]
    return [(queue_dir / name).expanduser().resolve() for name in DEFAULT_QUEUE_FILES]


def load_candidates(queue_files: Sequence[Path], include_queues: Sequence[str]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    include = {x.strip() for x in include_queues if x.strip()}
    for path in queue_files:
        if not path.exists() or path.stat().st_size == 0:
            continue
        for row in load_queue_geojson(path):
            queue = str(row.get("queue") or "")
            if include and queue not in include:
                continue
            candidates.append(row)
    candidates.sort(key=lambda r: (0 if r.get("queue") == "escalated" else 1, -score_value(r), str(r.get("candidate_id"))))
    return candidates


def load_checklist(path: Path) -> List[Dict[str, Any]]:
    payload = load_json(path)
    checklist = payload.get("checklist", [])
    if not isinstance(checklist, list) or not checklist:
        raise SystemExit(f"Context checklist missing or empty: {path}")
    return checklist


def md_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def coordinate_block(row: Dict[str, Any]) -> str:
    lon, lat = row.get("lon"), row.get("lat")
    x, y, crs = row.get("x"), row.get("y"), row.get("crs")
    lines = []
    if lon not in (None, "") and lat not in (None, ""):
        lines.append(f"- Lon/Lat: `{lon}, {lat}`")
    if x not in (None, "") and y not in (None, ""):
        lines.append(f"- Projected: `{x}, {y}`")
    if crs not in (None, ""):
        lines.append(f"- CRS: `{crs}`")
    if not lines:
        lines.append("- Coordinates: `not available in packet row`")
    return "\n".join(lines)


def write_candidate_brief(row: Dict[str, Any], checklist: Sequence[Dict[str, Any]], output_dir: Path, rank: int) -> Path:
    candidate_id = row.get("candidate_id") or f"candidate_{rank:04d}"
    queue = row.get("queue") or "unknown"
    packet_id = f"{rank:04d}_{slugify(queue)}_{slugify(candidate_id)}"
    path = output_dir / "briefs" / f"{packet_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append(f"# Follow-Up Packet: {candidate_id}")
    lines.append("")
    lines.append(f"Packet ID: `{packet_id}`")
    lines.append(f"Generated UTC: `{utc_now()}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for field in [
        "queue",
        "queue_reason",
        "ILAP_SCORE",
        "review_status",
        "review_decision",
        "review_confidence",
        "recommended_next_step",
        "evidence_tier",
    ]:
        lines.append(f"| {field} | {md_value(row.get(field))} |")

    lines.append("")
    lines.append("## Coordinates")
    lines.append("")
    lines.append(coordinate_block(row))

    lines.append("")
    lines.append("## Terrain / Context Summary")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for field in [
        "area_m2",
        "mean_slope_deg",
        "ring_mean_slope_deg",
        "tpi_mean_m",
        "terrain_visual_type",
        "access_context",
        "hydro_context",
        "utility_context",
        "karst_context",
        "imagery_context",
        "source_tile",
    ]:
        lines.append(f"| {field} | {md_value(row.get(field))} |")

    lines.append("")
    lines.append("## Review Notes")
    lines.append("")
    notes = row.get("review_notes")
    lines.append(str(notes) if notes else "No review notes supplied.")

    lines.append("")
    lines.append("## Context-Layer Checklist")
    lines.append("")
    lines.append("| Done | Layer | Evidence tier | Review question | Expected artifact |")
    lines.append("|---|---|---|---|---|")
    for item in checklist:
        lines.append(
            "| [ ] | {label} | {tier} | {question} | {artifact} |".format(
                label=md_value(item.get("label")),
                tier=md_value(item.get("evidence_tier")),
                question=md_value(item.get("question")),
                artifact=md_value(item.get("expected_artifact")),
            )
        )

    lines.append("")
    lines.append("## Analyst Disposition")
    lines.append("")
    lines.append("- [ ] Retain as follow-up candidate")
    lines.append("- [ ] Send to second reviewer")
    lines.append("- [ ] Downgrade after context review")
    lines.append("- [ ] Reject as ordinary/natural/artifact")
    lines.append("- [ ] Needs additional layer before decision")
    lines.append("")
    lines.append("Disposition notes:")
    lines.append("")
    lines.append("> ")

    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This packet is a follow-up review artifact only. It does not confirm infrastructure, hidden infrastructure, or subsurface activity. All escalations require cross-source validation.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    row["packet_id"] = packet_id
    row["brief_path"] = str(path)
    return path


def write_index_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow({
                "packet_id": row.get("packet_id", ""),
                "candidate_id": row.get("candidate_id", ""),
                "queue": row.get("queue", ""),
                "priority_rank": rank,
                "ILAP_SCORE": row.get("ILAP_SCORE", ""),
                "review_decision": row.get("review_decision", ""),
                "review_confidence": row.get("review_confidence", ""),
                "recommended_next_step": row.get("recommended_next_step", ""),
                "lon": row.get("lon", ""),
                "lat": row.get("lat", ""),
                "x": row.get("x", ""),
                "y": row.get("y", ""),
                "source_tile": row.get("source_tile", ""),
                "brief_path": row.get("brief_path", ""),
            })


def write_summary_md(path: Path, rows: Sequence[Dict[str, Any]], checklist: Sequence[Dict[str, Any]]) -> None:
    queue_counts = Counter(str(row.get("queue") or "unknown") for row in rows)
    decision_counts = Counter(str(row.get("review_decision") or "unknown") for row in rows)
    next_step_counts = Counter(str(row.get("recommended_next_step") or "unknown") for row in rows)

    lines: List[str] = []
    lines.append("# PR DEM Follow-Up Packet Summary")
    lines.append("")
    lines.append(f"Generated UTC: `{utc_now()}`")
    lines.append(f"Packet count: `{len(rows)}`")
    lines.append(f"Checklist item count: `{len(checklist)}`")
    lines.append("")
    for title, counts in [
        ("Queue counts", queue_counts),
        ("Review decision counts", decision_counts),
        ("Recommended next-step counts", next_step_counts),
    ]:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Value | Count |")
        lines.append("|---|---:|")
        for key, count in sorted(counts.items()):
            lines.append(f"| {md_value(key)} | {count} |")
        lines.append("")

    lines.append("## Packet index preview")
    lines.append("")
    lines.append("| Rank | Queue | Candidate | Score | Brief |")
    lines.append("|---:|---|---|---:|---|")
    for rank, row in enumerate(rows[:25], start=1):
        lines.append(f"| {rank} | {md_value(row.get('queue'))} | {md_value(row.get('candidate_id'))} | {md_value(row.get('ILAP_SCORE'))} | `{md_value(row.get('brief_path'))}` |")
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("Follow-up packets are review-management artifacts only. They do not confirm infrastructure, hidden infrastructure, or subsurface activity.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, inputs: Sequence[Path], outputs: Sequence[Path], row_count: int) -> None:
    payload = {
        "generated_at_utc": utc_now(),
        "tool": "tools/pr_dem_follow_up_packet_generator.py",
        "packet_count": row_count,
        "inputs": [
            {
                "path": str(p),
                "size_bytes": p.stat().st_size if p.exists() else None,
                "sha256": sha256_file(p) if p.exists() else None,
            }
            for p in inputs
        ],
        "outputs": [
            {
                "path": str(p),
                "size_bytes": p.stat().st_size if p.exists() else None,
                "sha256": sha256_file(p) if p.exists() else None,
            }
            for p in outputs
        ],
        "guardrail": "Packets are review-management artifacts only and require cross-source validation before escalation beyond analysis.",
    }
    write_json(path, payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate per-candidate follow-up markdown packets from routed PR DEM queues.")
    p.add_argument("--queue-dir", default=str(DEFAULT_QUEUE_DIR), help="Directory containing queue_escalated.geojson and queue_retained.geojson.")
    p.add_argument("--queue-file", action="append", default=[], help="Explicit queue GeoJSON file. May be repeated. Overrides default discovery when supplied.")
    p.add_argument("--include-queue", action="append", default=["escalated", "retained"], help="Queue name to include. May be repeated.")
    p.add_argument("--context-config", default=str(DEFAULT_CONTEXT_CONFIG), help="Context checklist JSON path.")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for briefs and indexes.")
    p.add_argument("--max-packets", type=int, default=0, help="Optional packet limit. 0 means no limit.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    queue_dir = Path(args.queue_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    context_path = Path(args.context_config).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not context_path.exists() or context_path.stat().st_size == 0:
        raise SystemExit(f"Missing context config: {context_path}")

    queue_files = discover_queue_files(queue_dir, args.queue_file)
    candidates = load_candidates(queue_files, args.include_queue)
    if args.max_packets and args.max_packets > 0:
        candidates = candidates[: args.max_packets]
    checklist = load_checklist(context_path)

    brief_paths: List[Path] = []
    for rank, row in enumerate(candidates, start=1):
        brief_paths.append(write_candidate_brief(row, checklist, output_dir, rank))

    index_csv = output_dir / "follow_up_index.csv"
    index_json = output_dir / "follow_up_index.json"
    summary_md = output_dir / "follow_up_packet_summary.md"
    manifest = output_dir / "follow_up_manifest.json"

    write_index_csv(index_csv, candidates)
    write_json(index_json, {"generated_at_utc": utc_now(), "packet_count": len(candidates), "packets": candidates})
    write_summary_md(summary_md, candidates, checklist)
    write_manifest(manifest, [context_path, *queue_files], [index_csv, index_json, summary_md, *brief_paths], len(candidates))

    print("Follow-up packet generation complete")
    print(f"Packet count: {len(candidates)}")
    print(f"Output dir: {output_dir}")
    print(f"Index CSV: {index_csv}")
    print(f"Summary: {summary_md}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
