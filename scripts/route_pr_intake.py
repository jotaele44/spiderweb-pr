#!/usr/bin/env python3
"""Domain router for Puerto Rico intake items.

Reads raw PR intake items from a JSONL file, classifies each by keyword matching
against configs/pr_intake_domain_router.yaml, and writes derivative CSVs plus a
routing summary to --out-dir.

Primary command (from repo root):
    python run_pr_intake_router.py --input <raw.jsonl> --out-dir <out/>

Equivalent:
    python scripts/route_pr_intake.py --input <raw.jsonl> --out-dir <out/>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER_CONFIG_PATH = REPO_ROOT / "configs" / "pr_intake_domain_router.yaml"

ROUTE_RESULTS_FILENAME = "route_results.jsonl"
SW_DERIVATIVES_FILENAME = "spiderweb_pr_derivatives.csv"
CS_DERIVATIVES_FILENAME = "contract_sweeper_derivatives.csv"
REVIEW_QUEUE_FILENAME = "manual_review_queue.csv"
SUMMARY_FILENAME = "routing_summary.json"

SW_RECORD_ID_PREFIX = "SW-PRINTAKE-"
CS_RECORD_ID_PREFIX = "CS-PRINTAKE-"

DERIVATIVE_FIELDS = (
    "record_id", "source_item_id", "target_repo", "canonical_repo",
    "related_repo_record_id", "source_name", "source_url",
    "published_at", "discovered_at", "title", "summary_own_words",
    "domains", "final_status", "output_tables",
    "evidence_tier", "confidence_level",
    "source_hash", "content_hash", "dedupe_group_id",
)

REVIEW_QUEUE_FIELDS = (
    "source_item_id", "title", "source_url", "reason",
)

DUAL_STATUSES = frozenset(("dual_routed_spiderweb_primary", "dual_routed_contract_primary"))


class RouterError(ValueError):
    pass


def _load_config() -> dict[str, Any]:
    if yaml is None:
        raise RouterError(
            "PyYAML is required to load the router config: pip install pyyaml"
        )
    try:
        return yaml.safe_load(ROUTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RouterError(f"router config not found: {ROUTER_CONFIG_PATH}") from exc


def _record_id(prefix: str, source_item_id: str) -> str:
    digest = hashlib.sha256(source_item_id.encode()).hexdigest()[:12]
    return f"{prefix}{digest}"


def _corpus(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("summary_own_words") or ""),
        str(item.get("body") or ""),
        str(item.get("source_url") or ""),
    ]
    return " ".join(parts).lower()


def _matched_rules(corpus: str, rules: list[dict]) -> list[dict]:
    matched = []
    for rule in rules:
        for kw in rule.get("keywords", []):
            # Word-boundary matching prevents short acronyms (epa, row, gis) from
            # matching as substrings of unrelated words (repair, growth, logistics).
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            if re.search(pattern, corpus):
                matched.append(rule)
                break
    return matched


def _domains_from_rules(rules: list[dict]) -> list[str]:
    seen: set[str] = set()
    domains: list[str] = []
    for rule in rules:
        for d in rule.get("domains", []):
            if d not in seen:
                seen.add(d)
                domains.append(d)
    return domains


def _output_tables_from_rules(rules: list[dict]) -> list[str]:
    seen: set[str] = set()
    tables: list[str] = []
    for rule in rules:
        for t in rule.get("output_tables", []):
            if t not in seen:
                seen.add(t)
                tables.append(t)
    return tables


def _check_dual_condition(domains: list[str], conditions: list[dict]) -> dict | None:
    domain_set = set(domains)
    for cond in conditions:
        required = set(cond.get("if_domains_include", []))
        if required and required.issubset(domain_set):
            return cond
    return None


def _route_item(
    item: dict[str, Any],
    config: dict[str, Any],
    fail_on_errors: bool,
) -> dict[str, Any]:
    source_item_id = str(item.get("source_item_id") or "")
    if not source_item_id:
        if fail_on_errors:
            raise RouterError(f"item missing source_item_id: {item!r}")
        return {
            "source_item_id": "", "final_status": "manual_review_required",
            "reason": "missing source_item_id", "canonical_repo": "",
            "derivative_repo": "", "domains": [], "output_tables": [],
            "sw_record_id": "", "cs_record_id": "",
        }

    corpus = _corpus(item)
    rules: list[dict] = config.get("routing_rules", [])
    dual_conditions: list[dict] = config.get("dual_route_conditions", [])

    matched = _matched_rules(corpus, rules)
    sw_rules = [r for r in matched if r.get("canonical_repo") == "spiderweb-pr"]
    cs_rules = [r for r in matched if r.get("canonical_repo") == "Contract-Sweeper"]

    sw_record_id = _record_id(SW_RECORD_ID_PREFIX, source_item_id)
    cs_record_id = _record_id(CS_RECORD_ID_PREFIX, source_item_id)

    if sw_rules and cs_rules:
        all_domains = _domains_from_rules(matched)
        all_tables = _output_tables_from_rules(matched)
        cond = _check_dual_condition(all_domains, dual_conditions)
        canonical = cond["canonical_repo"] if cond else "spiderweb-pr"
        derivative = cond.get("derivative_repo", "") if cond else "Contract-Sweeper"
        status = (
            "dual_routed_contract_primary"
            if canonical == "Contract-Sweeper"
            else "dual_routed_spiderweb_primary"
        )
        return {
            "source_item_id": source_item_id, "final_status": status, "reason": "",
            "canonical_repo": canonical, "derivative_repo": derivative,
            "domains": all_domains, "output_tables": all_tables,
            "sw_record_id": sw_record_id, "cs_record_id": cs_record_id,
        }

    if sw_rules:
        return {
            "source_item_id": source_item_id, "final_status": "routed_spiderweb_pr",
            "reason": "", "canonical_repo": "spiderweb-pr", "derivative_repo": "",
            "domains": _domains_from_rules(sw_rules),
            "output_tables": _output_tables_from_rules(sw_rules),
            "sw_record_id": sw_record_id, "cs_record_id": "",
        }

    if cs_rules:
        return {
            "source_item_id": source_item_id, "final_status": "routed_contract_sweeper",
            "reason": "", "canonical_repo": "Contract-Sweeper", "derivative_repo": "",
            "domains": _domains_from_rules(cs_rules),
            "output_tables": _output_tables_from_rules(cs_rules),
            "sw_record_id": "", "cs_record_id": cs_record_id,
        }

    return {
        "source_item_id": source_item_id, "final_status": "manual_review_required",
        "reason": "no keyword match", "canonical_repo": "", "derivative_repo": "",
        "domains": [], "output_tables": [], "sw_record_id": "", "cs_record_id": "",
    }


def _derivative_row(
    item: dict[str, Any],
    result: dict[str, Any],
    target_repo: str,
    own_record_id: str,
    related_record_id: str,
) -> dict[str, str]:
    return {
        "record_id": own_record_id,
        "source_item_id": result["source_item_id"],
        "target_repo": target_repo,
        "canonical_repo": result["canonical_repo"],
        "related_repo_record_id": related_record_id,
        "source_name": str(item.get("source_name") or ""),
        "source_url": str(item.get("source_url") or ""),
        "published_at": str(item.get("published_at") or ""),
        "discovered_at": str(item.get("discovered_at") or ""),
        "title": str(item.get("title") or ""),
        "summary_own_words": str(item.get("summary_own_words") or ""),
        "domains": json.dumps(result["domains"], ensure_ascii=False),
        "final_status": result["final_status"],
        "output_tables": json.dumps(result["output_tables"], ensure_ascii=False),
        "evidence_tier": str(item.get("evidence_tier") or ""),
        "confidence_level": str(item.get("confidence_level") or ""),
        "source_hash": str(item.get("source_hash") or ""),
        "content_hash": str(item.get("content_hash") or ""),
        "dedupe_group_id": str(item.get("dedupe_group_id") or ""),
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def route(
    input_path: str | Path,
    out_dir: str | Path,
    fail_on_validation_errors: bool = False,
) -> dict[str, Any]:
    """Route raw PR intake items to their canonical repos.

    Reads JSONL from *input_path*, classifies each item, and writes five output
    files to *out_dir*. Returns the routing summary dict.
    """
    config = _load_config()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_text = Path(input_path).read_text(encoding="utf-8")
    items: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if fail_on_validation_errors:
                raise RouterError(f"invalid JSON in input: {exc}") from exc

    route_results: list[dict[str, Any]] = []
    sw_rows: list[dict[str, str]] = []
    cs_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    status_counts: Counter = Counter()

    for item in items:
        result = _route_item(item, config, fail_on_validation_errors)
        status = result["final_status"]
        status_counts[status] += 1

        route_results.append({
            "source_item_id": result["source_item_id"],
            "final_status": status,
            "canonical_repo": result["canonical_repo"],
            "derivative_repo": result.get("derivative_repo", ""),
            "domains": result["domains"],
            "output_tables": result["output_tables"],
            "sw_record_id": result.get("sw_record_id", ""),
            "cs_record_id": result.get("cs_record_id", ""),
        })

        if status == "routed_spiderweb_pr":
            sw_rows.append(_derivative_row(
                item, result, "spiderweb-pr",
                result["sw_record_id"], result["cs_record_id"],
            ))
        elif status == "routed_contract_sweeper":
            cs_rows.append(_derivative_row(
                item, result, "Contract-Sweeper",
                result["cs_record_id"], result["sw_record_id"],
            ))
        elif status in DUAL_STATUSES:
            sw_rows.append(_derivative_row(
                item, result, "spiderweb-pr",
                result["sw_record_id"], result["cs_record_id"],
            ))
            cs_rows.append(_derivative_row(
                item, result, "Contract-Sweeper",
                result["cs_record_id"], result["sw_record_id"],
            ))
        elif status == "manual_review_required":
            review_rows.append({
                "source_item_id": result["source_item_id"],
                "title": str(item.get("title") or ""),
                "source_url": str(item.get("source_url") or ""),
                "reason": result.get("reason", ""),
            })

    _write_jsonl(out / ROUTE_RESULTS_FILENAME, route_results)
    _write_csv(out / SW_DERIVATIVES_FILENAME, sw_rows, DERIVATIVE_FIELDS)
    _write_csv(out / CS_DERIVATIVES_FILENAME, cs_rows, DERIVATIVE_FIELDS)
    _write_csv(out / REVIEW_QUEUE_FILENAME, review_rows, REVIEW_QUEUE_FIELDS)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "router_version": str(config.get("version", "unknown")),
        "input_count": len(items),
        "spiderweb_pr_derivative_count": len(sw_rows),
        "contract_sweeper_derivative_count": len(cs_rows),
        "manual_review_count": len(review_rows),
        "by_status": dict(sorted(status_counts.items())),
        "zero_loss_pass": sum(status_counts.values()) == len(items),
        "outputs": {
            "route_results": ROUTE_RESULTS_FILENAME,
            "spiderweb_pr_derivatives": SW_DERIVATIVES_FILENAME,
            "contract_sweeper_derivatives": CS_DERIVATIVES_FILENAME,
            "manual_review_queue": REVIEW_QUEUE_FILENAME,
        },
    }
    (out / SUMMARY_FILENAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", required=True,
                        help="JSONL file of raw PR intake items")
    parser.add_argument("--out-dir", required=True,
                        help="Output directory for derivative CSVs and routing summary")
    parser.add_argument("--fail-on-validation-errors", action="store_true",
                        help="Abort on first invalid or unclassifiable item")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = route(args.input, args.out_dir, args.fail_on_validation_errors)
    except RouterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["zero_loss_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
