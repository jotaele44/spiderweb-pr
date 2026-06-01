#!/usr/bin/env python3
"""Regional expansion controller for PR DEM terrain-screening batches.

Reads post-review queue and packet artifacts, scores configured regional batch
profiles, and exports an expansion priority matrix. This is a planning tool; it
does not execute DEM batches.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_PROFILE_CONFIG = Path("configs") / "pr_dem_batch_profiles.json"
DEFAULT_QUEUE_SUMMARY = Path("outputs") / "pr_dem_review_queues" / "queue_summary.json"
DEFAULT_PACKET_INDEX = Path("outputs") / "pr_dem_follow_up_packets" / "follow_up_index.json"
DEFAULT_OUTPUT_DIR = Path("outputs") / "pr_dem_expansion_controller"

MATRIX_FIELDS = [
    "rank",
    "profile",
    "label",
    "current_status",
    "proposed_status",
    "priority",
    "expansion_score",
    "recommendation",
    "rationale",
    "bbox_wgs84",
    "purpose",
    "notes",
]

STATUS_BASE = {
    "active_pilot": 15,
    "queued_profile": 35,
    "ready_next": 45,
    "deferred": 10,
    "completed": -100,
    "paused": -25,
    "rejected": -100,
}

KEYWORD_BONUS = {
    "karst": ["karst", "closed_depression", "sinkhole", "geology"],
    "urban": ["urban", "ordinary_infrastructure", "building", "road_cut", "artifact"],
    "mountain": ["ridge", "summit", "slope", "bench", "terrace", "central"],
    "hydro": ["hydro", "reservoir", "stream", "water", "drainage"],
    "utility": ["utility", "powerline", "substation", "tower", "pipeline"],
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", " ", str(value or "").lower())


def load_profiles(path: Path) -> Dict[str, Any]:
    payload = load_json(path)
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise SystemExit(f"No profiles found in {path}")
    return payload


def signal_from_queue_summary(queue_summary: Dict[str, Any]) -> Dict[str, Any]:
    queue_counts = queue_summary.get("queue_counts", {}) if isinstance(queue_summary, dict) else {}
    score_by_queue = queue_summary.get("score_by_queue", {}) if isinstance(queue_summary, dict) else {}
    return {
        "escalated_count": as_int(queue_counts.get("escalated")),
        "retained_count": as_int(queue_counts.get("retained")),
        "second_pass_count": as_int(queue_counts.get("second_pass")),
        "insufficient_evidence_count": as_int(queue_counts.get("insufficient_evidence")),
        "rejected_count": as_int(queue_counts.get("rejected")),
        "unreviewed_count": as_int(queue_counts.get("unreviewed")),
        "escalated_mean_score": as_float((score_by_queue.get("escalated") or {}).get("mean")),
        "retained_mean_score": as_float((score_by_queue.get("retained") or {}).get("mean")),
    }


def packet_rows(packet_index: Dict[str, Any]) -> List[Dict[str, Any]]:
    packets = packet_index.get("packets", []) if isinstance(packet_index, dict) else []
    return packets if isinstance(packets, list) else []


def signal_from_packets(packet_index: Dict[str, Any]) -> Dict[str, Any]:
    rows = packet_rows(packet_index)
    q = Counter(str(row.get("queue") or "unknown") for row in rows)
    decisions = Counter(str(row.get("review_decision") or "unknown") for row in rows)
    next_steps = Counter(str(row.get("recommended_next_step") or "unknown") for row in rows)
    contexts = Counter()
    for row in rows:
        for field in [
            "terrain_visual_type",
            "access_context",
            "hydro_context",
            "utility_context",
            "karst_context",
            "imagery_context",
            "review_notes",
            "recommended_next_step",
            "source_tile",
        ]:
            text = normalize_text(row.get(field))
            for token in text.split():
                if len(token) >= 4:
                    contexts[token] += 1
    return {
        "packet_count": len(rows),
        "packet_queue_counts": dict(q),
        "packet_decision_counts": dict(decisions),
        "packet_next_step_counts": dict(next_steps),
        "context_token_counts": dict(contexts),
    }


def global_readiness_score(queue_signal: Dict[str, Any], packet_signal: Dict[str, Any]) -> Tuple[float, List[str]]:
    escalated = queue_signal["escalated_count"]
    retained = queue_signal["retained_count"]
    second_pass = queue_signal["second_pass_count"]
    insufficient = queue_signal["insufficient_evidence_count"]
    unreviewed = queue_signal["unreviewed_count"]
    packets = packet_signal["packet_count"]

    score = 0.0
    reasons: List[str] = []

    if escalated > 0:
        bonus = min(30, escalated * 6)
        score += bonus
        reasons.append(f"escalated queue present (+{bonus})")
    if retained > 0:
        bonus = min(20, retained * 2)
        score += bonus
        reasons.append(f"retained queue present (+{bonus})")
    if packets > 0:
        bonus = min(20, packets * 2)
        score += bonus
        reasons.append(f"follow-up packets generated (+{bonus})")
    if second_pass > escalated + retained:
        score -= 15
        reasons.append("second-pass queue larger than retained/escalated (-15)")
    if insufficient > escalated + retained:
        score -= 10
        reasons.append("insufficient-evidence queue dominates (-10)")
    if unreviewed > 0:
        penalty = min(15, unreviewed)
        score -= penalty
        reasons.append(f"unreviewed candidates remain (-{penalty})")

    if not reasons:
        reasons.append("no queue/packet signal available")
    return score, reasons


def profile_keyword_bonus(profile: Dict[str, Any], packet_signal: Dict[str, Any]) -> Tuple[float, List[str]]:
    text = normalize_text(" ".join(str(profile.get(k, "")) for k in ["label", "purpose", "notes", "status"]))
    tokens = packet_signal.get("context_token_counts", {}) or {}
    bonus = 0.0
    reasons: List[str] = []
    for group, keywords in KEYWORD_BONUS.items():
        profile_hits = [kw for kw in keywords if kw in text]
        if not profile_hits:
            continue
        signal_hits = sum(as_int(tokens.get(kw, 0)) for kw in keywords)
        if signal_hits > 0:
            value = min(12, 2 * signal_hits)
            bonus += value
            reasons.append(f"{group} keyword convergence (+{value})")
    return bonus, reasons


def recommendation_from_score(score: float, status: str) -> Tuple[str, str]:
    if status in {"completed", "rejected"}:
        return "do_not_run", "profile is already completed or rejected"
    if score >= 75:
        return "run_next", "highest-priority expansion candidate"
    if score >= 55:
        return "ready_after_review", "run after review of expansion matrix"
    if score >= 35:
        return "hold_for_more_signal", "needs stronger queue/packet support"
    return "defer", "insufficient reviewed signal for expansion"


def proposed_status(recommendation: str, current_status: str, completed_profile: Optional[str], profile_name: str) -> str:
    if completed_profile and profile_name == completed_profile:
        return "completed"
    if current_status in {"completed", "rejected"}:
        return current_status
    if recommendation == "run_next":
        return "ready_next"
    if recommendation == "ready_after_review":
        return "queued_profile"
    if recommendation == "hold_for_more_signal":
        return "deferred"
    return "deferred"


def score_profiles(
    profiles_payload: Dict[str, Any],
    queue_signal: Dict[str, Any],
    packet_signal: Dict[str, Any],
    completed_profile: Optional[str],
) -> List[Dict[str, Any]]:
    global_score, global_reasons = global_readiness_score(queue_signal, packet_signal)
    rows: List[Dict[str, Any]] = []
    profiles = profiles_payload.get("profiles", {})

    for name, profile in profiles.items():
        status = str(profile.get("status", "queued_profile"))
        priority = as_int(profile.get("priority"), 999)
        base = STATUS_BASE.get(status, 20)
        priority_bonus = max(0, 30 - min(priority, 30))
        keyword_bonus, keyword_reasons = profile_keyword_bonus(profile, packet_signal)
        score = base + priority_bonus + global_score + keyword_bonus
        recommendation, rec_reason = recommendation_from_score(score, status)
        pstatus = proposed_status(recommendation, status, completed_profile, name)
        rationale = "; ".join([rec_reason, *global_reasons, *keyword_reasons])
        rows.append({
            "profile": name,
            "label": profile.get("label", name),
            "current_status": status,
            "proposed_status": pstatus,
            "priority": priority,
            "expansion_score": round(score, 3),
            "recommendation": recommendation,
            "rationale": rationale,
            "bbox_wgs84": json.dumps(profile.get("bbox_wgs84", [])),
            "purpose": profile.get("purpose", ""),
            "notes": profile.get("notes", ""),
        })

    rows.sort(key=lambda r: (r["recommendation"] != "run_next", -as_float(r["expansion_score"]), as_int(r["priority"], 999), str(r["profile"])))
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows


def write_matrix_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MATRIX_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MATRIX_FIELDS})


def build_updated_profiles(profiles_payload: Dict[str, Any], rows: Sequence[Dict[str, Any]], completed_profile: Optional[str]) -> Dict[str, Any]:
    payload = deepcopy(profiles_payload)
    payload["generated_at_utc"] = utc_now()
    payload["status_update_mode"] = "proposed_not_applied"
    payload["status_update_note"] = "Review this proposed file before replacing configs/pr_dem_batch_profiles.json."
    status_by_profile = {row["profile"]: row["proposed_status"] for row in rows}
    for name, profile in payload.get("profiles", {}).items():
        if name in status_by_profile:
            profile["status"] = status_by_profile[name]
            profile["last_expansion_controller_status"] = status_by_profile[name]
            profile["last_expansion_controller_run_utc"] = payload["generated_at_utc"]
    if completed_profile:
        payload["last_completed_profile"] = completed_profile
    return payload


def md_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|")


def write_recommendation_md(
    path: Path,
    rows: Sequence[Dict[str, Any]],
    queue_signal: Dict[str, Any],
    packet_signal: Dict[str, Any],
) -> None:
    top = rows[0] if rows else {}
    lines: List[str] = []
    lines.append("# PR DEM Regional Expansion Recommendation")
    lines.append("")
    lines.append(f"Generated UTC: `{utc_now()}`")
    lines.append("")
    lines.append("## Top recommendation")
    lines.append("")
    if top:
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for field in ["rank", "profile", "label", "recommendation", "expansion_score", "current_status", "proposed_status", "rationale"]:
            lines.append(f"| {field} | {md_escape(top.get(field, ''))} |")
    else:
        lines.append("No profiles available.")

    lines.append("")
    lines.append("## Signal summary")
    lines.append("")
    lines.append("| Signal | Value |")
    lines.append("|---|---:|")
    for key, value in queue_signal.items():
        lines.append(f"| queue.{key} | {value} |")
    lines.append(f"| packets.packet_count | {packet_signal.get('packet_count', 0)} |")

    lines.append("")
    lines.append("## Expansion priority matrix")
    lines.append("")
    lines.append("| Rank | Profile | Status | Proposed | Score | Recommendation |")
    lines.append("|---:|---|---|---|---:|---|")
    for row in rows:
        lines.append(
            f"| {row.get('rank')} | {row.get('profile')} | {row.get('current_status')} | {row.get('proposed_status')} | {row.get('expansion_score')} | {row.get('recommendation')} |"
        )

    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This controller ranks next batch profiles for review. It does not execute DEM processing.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, inputs: Sequence[Path], outputs: Sequence[Path], rows: Sequence[Dict[str, Any]]) -> None:
    payload = {
        "generated_at_utc": utc_now(),
        "tool": "tools/pr_dem_regional_expansion_controller.py",
        "profile_count": len(rows),
        "top_profile": rows[0].get("profile") if rows else None,
        "top_recommendation": rows[0].get("recommendation") if rows else None,
        "inputs": [
            {
                "path": str(p),
                "exists": p.exists(),
                "size_bytes": p.stat().st_size if p.exists() else None,
                "sha256": sha256_file(p),
            }
            for p in inputs
        ],
        "outputs": [
            {
                "path": str(p),
                "exists": p.exists(),
                "size_bytes": p.stat().st_size if p.exists() else None,
                "sha256": sha256_file(p),
            }
            for p in outputs
        ],
        "guardrail": "Expansion matrix is a decision-support artifact only. Run batches manually after review.",
    }
    write_json(path, payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Score next PR DEM regional batch profiles from reviewed queue and packet artifacts.")
    p.add_argument("--profiles", default=str(DEFAULT_PROFILE_CONFIG), help="Batch profile config JSON.")
    p.add_argument("--queue-summary", default=str(DEFAULT_QUEUE_SUMMARY), help="queue_summary.json from review decision router.")
    p.add_argument("--packet-index", default=str(DEFAULT_PACKET_INDEX), help="follow_up_index.json from packet generator.")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for expansion matrix artifacts.")
    p.add_argument("--completed-profile", default="", help="Optional profile name to mark completed in proposed status output, e.g. arecibo_utuado.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    profile_path = Path(args.profiles).expanduser().resolve()
    queue_path = Path(args.queue_summary).expanduser().resolve()
    packet_path = Path(args.packet_index).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    profiles_payload = load_profiles(profile_path)
    queue_summary = load_json(queue_path, default={})
    packet_index = load_json(packet_path, default={})
    queue_signal = signal_from_queue_summary(queue_summary)
    packet_signal = signal_from_packets(packet_index)

    completed_profile = args.completed_profile.strip() or None
    rows = score_profiles(profiles_payload, queue_signal, packet_signal, completed_profile)
    updated_profiles = build_updated_profiles(profiles_payload, rows, completed_profile)

    matrix_csv = output_dir / "expansion_priority_matrix.csv"
    matrix_json = output_dir / "expansion_priority_matrix.json"
    recommendation_md = output_dir / "expansion_recommendation.md"
    proposed_profiles = output_dir / "updated_batch_profiles.proposed.json"
    manifest = output_dir / "expansion_controller_manifest.json"

    write_matrix_csv(matrix_csv, rows)
    write_json(matrix_json, {"generated_at_utc": utc_now(), "queue_signal": queue_signal, "packet_signal": packet_signal, "profiles": rows})
    write_recommendation_md(recommendation_md, rows, queue_signal, packet_signal)
    write_json(proposed_profiles, updated_profiles)
    write_manifest(manifest, [profile_path, queue_path, packet_path], [matrix_csv, matrix_json, recommendation_md, proposed_profiles], rows)

    print("Regional expansion controller complete")
    print(f"Profiles scored: {len(rows)}")
    if rows:
        print(f"Top profile: {rows[0]['profile']} ({rows[0]['recommendation']}, score={rows[0]['expansion_score']})")
    print(f"Matrix CSV: {matrix_csv}")
    print(f"Recommendation: {recommendation_md}")
    print(f"Proposed profile statuses: {proposed_profiles}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
