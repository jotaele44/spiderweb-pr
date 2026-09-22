#!/usr/bin/env python3
"""Live, read-only JP flood V3 drift and reproducibility checks.

No mode in this script mutates frozen source states or certification receipts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACQUIRE_PATH = ROOT / "scripts" / "acquire_jp_flood_documents.py"
_spec = importlib.util.spec_from_file_location("jp_flood_acquire", ACQUIRE_PATH)
acquire = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(acquire)

Q_FALLBACK_URLS = (
    "https://docs.pr.gov/files/JP-Junta%20de%20Planificacion/Planes%20de%20Mitigaci%C3%B3n%20Aprobados/Actualizados%20por%20los%20municipios/Queb-Approved-HMP.pdf",
    acquire.QUEBRADILLAS_HMP_PROVENANCE_URL,
)
FLORIDA_FALLBACK_URLS = (
    acquire.FLORIDA_HMP_URL,
    "https://docs.pr.gov/files/JP-Junta%20de%20Planificacion/Planes%20de%20Mitigaci%C3%B3n%20Aprobados/Actualizados%20por%20los%20municipios/Flor-Plan-Approved-HMP.pdf",
)


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    print(text, end="")
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _fetch_to(url: str, path: Path, timeout: int = 240) -> dict[str, Any]:
    req = urllib.request.Request(
        urllib.parse.quote(url, safe=":/?&=%"),
        headers={"User-Agent": "spiderweb-pr-jp-flood-v3-live/1.0"},
    )
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=timeout) as response, path.open("wb") as out:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            h.update(block)
            out.write(block)
        return {
            "final_url": response.geturl(),
            "byte_size": path.stat().st_size,
            "sha256": h.hexdigest(),
        }


def resolve_quebradillas(root: Path) -> Path:
    target = root / "Quebradillas.pdf"
    errors = []
    for url in Q_FALLBACK_URLS:
        candidate = root / "Quebradillas.candidate.pdf"
        candidate.unlink(missing_ok=True)
        try:
            receipt = _fetch_to(url, candidate)
            if (
                receipt["byte_size"] == acquire.QUEBRADILLAS_FROZEN_BYTE_SIZE
                and receipt["sha256"] == acquire.QUEBRADILLAS_FROZEN_SHA256
            ):
                candidate.replace(target)
                return target
            errors.append({"url": url, "state": "HASH_OR_SIZE_MISMATCH", **receipt})
        except Exception as exc:
            errors.append({"url": url, "state": "TRANSPORT_BLOCKED", "error": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(f"QUEBRADILLAS_FALLBACK_UNRESOLVED {json.dumps(errors)}")


def transition_check(report: Path | None) -> int:
    payload: dict[str, Any] = {
        "schema_version": "spiderweb.jp-flood-source-transition/v1",
        "status": "PASS",
        "transitions": [],
    }
    try:
        portal_bytes, _, final_url = acquire.fetch_bytes(acquire.PORTAL_URL, 180)
        rows = acquire.discover_series(portal_bytes.decode("utf-8", "ignore"), final_url)
    except Exception as exc:
        payload["status"] = "TRANSPORT_BLOCKED"
        payload["error"] = f"{type(exc).__name__}: {exc}"
        _write(report, payload)
        return 3

    listed = {row["municipality"]: row for row in rows}
    payload["listed_count"] = len(rows)

    if len(rows) != acquire.EXPECTED_LISTED:
        payload["transitions"].append({
            "kind": "SOURCE_SERIES_DENOMINATOR_CHANGED",
            "expected": acquire.EXPECTED_LISTED,
            "observed": len(rows),
        })
    if "Florida" in listed:
        payload["transitions"].append({
            "municipality": "Florida",
            "kind": "NOT_LISTED_TO_LISTED",
            "action": "REQUIRES_READJUDICATION",
        })
    q = listed.get("Quebradillas")
    if q is None:
        payload["transitions"].append({
            "municipality": "Quebradillas",
            "kind": "LISTED_TO_NOT_LISTED",
            "action": "REQUIRES_READJUDICATION",
        })
    else:
        url = q["source_url"]
        try:
            req = urllib.request.Request(
                acquire._encoded(url),
                method="HEAD",
                headers={"User-Agent": acquire.UA},
            )
            with urllib.request.urlopen(req, timeout=90) as response:
                payload["transitions"].append({
                    "municipality": "Quebradillas",
                    "kind": "CANONICAL_MANIFESTATION_RECOVERED",
                    "http_status": getattr(response, "status", 200),
                    "final_url": response.geturl(),
                    "action": "REQUIRES_READJUDICATION",
                })
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                payload["quebradillas_canonical_state"] = "STILL_MISSING"
            else:
                payload["status"] = "TRANSPORT_BLOCKED"
                payload["quebradillas_probe"] = {"http_status": exc.code, "url": url}
        except Exception as exc:
            payload["status"] = "TRANSPORT_BLOCKED"
            payload["quebradillas_probe"] = {"error": f"{type(exc).__name__}: {exc}", "url": url}

    if payload["transitions"]:
        payload["status"] = "REQUIRES_READJUDICATION"
        _write(report, payload)
        return 2
    _write(report, payload)
    return 0 if payload["status"] == "PASS" else 3


def replica(out: Path, workdir: Path) -> int:
    workdir.mkdir(parents=True, exist_ok=True)
    raw = workdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": "spiderweb.jp-flood-reproducibility-replica/v1",
        "status": "PASS",
        "documents": [],
        "failures": [],
    }

    try:
        q_path = resolve_quebradillas(workdir)
        portal_bytes, _, final_url = acquire.fetch_bytes(acquire.PORTAL_URL, 180)
        rows = acquire.apply_source_states(
            acquire.discover_series(portal_bytes.decode("utf-8", "ignore"), final_url)
        )
        acquire.validate(rows)
    except Exception as exc:
        report["status"] = "TRANSPORT_BLOCKED"
        report["failures"].append({"phase": "bootstrap", "error": f"{type(exc).__name__}: {exc}"})
        _write(out, report)
        return 3

    for row in sorted(rows, key=lambda r: acquire._key(r["municipality"])):
        municipality = row["municipality"]
        use_fallback = row["source_state"] != "AVAILABLE"
        operational_class = row.get("fallback_document_class") if use_fallback else row.get("document_class")
        try:
            if municipality == "Quebradillas":
                target = raw / acquire.QUEBRADILLAS_FROZEN_FILENAME
                shutil.copy2(q_path, target)
                receipt = acquire.verify_frozen_quebradillas(target)
            else:
                urls = FLORIDA_FALLBACK_URLS if municipality == "Florida" else (row["source_url"],)
                receipt = None
                errors = []
                for url in urls:
                    if not url:
                        continue
                    filename = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]) or f"{municipality}.pdf"
                    try:
                        receipt = acquire.acquire_resume_safe(url, raw / filename, 240)
                        break
                    except Exception as exc:
                        errors.append(f"{url} => {type(exc).__name__}: {exc}")
                if receipt is None:
                    raise RuntimeError(" | ".join(errors))
            report["documents"].append({
                "municipality": municipality,
                "source_state": row["source_state"],
                "operational_document_class": operational_class,
                "filename": receipt["filename"],
                "byte_size": receipt["byte_size"],
                "sha256": receipt["sha256"],
            })
        except Exception as exc:
            report["failures"].append({
                "municipality": municipality,
                "state": "TRANSPORT_BLOCKED",
                "error": f"{type(exc).__name__}: {exc}",
            })

    if report["failures"]:
        report["status"] = "TRANSPORT_BLOCKED"
    if len(report["documents"]) != 78:
        report["status"] = "TRANSPORT_BLOCKED"
    _write(out, report)
    return 0 if report["status"] == "PASS" else 3


def _baseline(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            row["byte_size"] = int(row["byte_size"])
            rows[row["municipality"]] = row
    return rows


def compare(replica_a: Path, replica_b: Path, baseline_path: Path, report: Path | None) -> int:
    a = json.loads(replica_a.read_text(encoding="utf-8"))
    b = json.loads(replica_b.read_text(encoding="utf-8"))
    base = _baseline(baseline_path)
    payload: dict[str, Any] = {
        "schema_version": "spiderweb.jp-flood-reproducibility-compare/v1",
        "status": "PASS",
        "classifications": [],
    }

    if a.get("status") != "PASS" or b.get("status") != "PASS":
        payload["status"] = "TRANSPORT_BLOCKED"
        payload["replica_status"] = {"a": a.get("status"), "b": b.get("status")}
        _write(report, payload)
        return 3

    amap = {r["municipality"]: r for r in a["documents"]}
    bmap = {r["municipality"]: r for r in b["documents"]}
    if set(amap) != set(bmap) or set(amap) != set(base):
        payload["status"] = "REQUIRES_READJUDICATION"
        payload["classifications"].append({"kind": "DENOMINATOR_DIVERGENCE"})
        _write(report, payload)
        return 2

    core = ("source_state", "operational_document_class", "filename", "byte_size", "sha256")
    for municipality in sorted(amap):
        ar, br, frozen = amap[municipality], bmap[municipality], base[municipality]
        if any(ar[k] != br[k] for k in core):
            payload["classifications"].append({
                "municipality": municipality,
                "kind": "REPLICA_DIVERGENCE",
                "replica_a": {k: ar[k] for k in core},
                "replica_b": {k: br[k] for k in core},
            })
            continue
        if ar["source_state"] != frozen["source_state"] or ar["operational_document_class"] != frozen["operational_document_class"]:
            payload["classifications"].append({
                "municipality": municipality,
                "kind": "SOURCE_STATE_CHANGED",
            })
        elif ar["sha256"] != frozen["sha256"] or ar["byte_size"] != int(frozen["byte_size"]):
            payload["classifications"].append({
                "municipality": municipality,
                "kind": "REMOTE_BYTES_CHANGED",
                "frozen_sha256": frozen["sha256"],
                "observed_sha256": ar["sha256"],
            })
        elif ar["filename"] != frozen["filename"]:
            payload["classifications"].append({
                "municipality": municipality,
                "kind": "REMOTE_METADATA_CHANGED_ONLY",
            })
        else:
            payload["classifications"].append({
                "municipality": municipality,
                "kind": "IDENTICAL",
            })

    blocking = [
        x for x in payload["classifications"]
        if x["kind"] in {"REPLICA_DIVERGENCE", "SOURCE_STATE_CHANGED", "REMOTE_BYTES_CHANGED"}
    ]
    payload["blocking_count"] = len(blocking)
    payload["identical_count"] = sum(x["kind"] == "IDENTICAL" for x in payload["classifications"])
    payload["metadata_only_count"] = sum(x["kind"] == "REMOTE_METADATA_CHANGED_ONLY" for x in payload["classifications"])
    if blocking:
        payload["status"] = "REQUIRES_READJUDICATION"
        _write(report, payload)
        return 2
    _write(report, payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)

    p_transition = sub.add_parser("transition")
    p_transition.add_argument("--report", type=Path)

    p_replica = sub.add_parser("replica")
    p_replica.add_argument("--out", type=Path, required=True)
    p_replica.add_argument("--workdir", type=Path, required=True)

    p_compare = sub.add_parser("compare")
    p_compare.add_argument("--a", type=Path, required=True)
    p_compare.add_argument("--b", type=Path, required=True)
    p_compare.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "data/jp_flood_documents/certification/2026-09-21/byte-ledger.csv",
    )
    p_compare.add_argument("--report", type=Path)

    args = parser.parse_args()
    if args.mode == "transition":
        return transition_check(args.report)
    if args.mode == "replica":
        return replica(args.out, args.workdir)
    return compare(args.a, args.b, args.baseline, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
