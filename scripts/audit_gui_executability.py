#!/usr/bin/env python3
"""Side-effect-free GUI executability auditor.

This auditor NEVER imports or executes target application code. It discovers
app-authored interactive JSX/TSX controls, records raw manifestations, and
classifies only what the source text can prove. Regex/lexical discovery is
explicitly non-canonical and ambiguous cases fail closed to UNRESOLVED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "1.0.0-poc"
FINAL_STATES = {"WIRED", "DEAD_SURFACE", "STUB", "UNRESOLVED"}
SIDE_EFFECT_CLASS = "UNKNOWN_BLOCKED"
SOURCE_SUFFIXES = {".jsx", ".tsx"}
BUTTON_RE = re.compile(r"<button\b(?P<attrs>[^>]*)>(?P<body>.*?)</button\s*>", re.I | re.S)
ONCLICK_RE = re.compile(r"\bonClick\s*=\s*\{(?P<expr>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", re.S)
TYPE_RE = re.compile(r"\btype\s*=\s*[\"'](?P<type>[^\"']+)[\"']", re.I)
DISABLED_RE = re.compile(r"\bdisabled(?:\s*=\s*(?:\{?true\}?|[\"']disabled[\"']))?\b", re.I)
IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$")
STUB_PATTERNS = (
    re.compile(r"\bthrow\s+new\s+Error\s*\(\s*[\"'](?:TODO|NOT IMPLEMENTED|not implemented)", re.I),
    re.compile(r"\bconsole\.(?:log|warn)\s*\(\s*[\"']TODO\b", re.I),
)


@dataclass(frozen=True)
class Manifestation:
    manifestation_id: str
    source_path: str
    line: int
    raw_label: str
    normalized_label: str
    control_type: str
    handler_expression: str | None
    handler_symbol: str | None
    side_effect_class: str
    evidence_tier: str
    final_state: str
    gap_codes: tuple[str, ...]
    limitations: tuple[str, ...]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strip_jsx_label(body: str) -> str:
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\{[^{}]*\}", " {expr} ", body)
    return " ".join(body.split()).strip()


def normalize_label(raw: str) -> str:
    return " ".join(raw.casefold().split())


def line_for(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_function_body(text: str, symbol: str) -> str | None:
    """Bounded lexical lookup. Discovery only; never treated as semantic identity."""
    leaf = symbol.split(".")[-1]
    patterns = [
        re.compile(rf"(?:const|let|var)\s+{re.escape(leaf)}\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{{", re.M),
        re.compile(rf"(?:async\s+)?function\s+{re.escape(leaf)}\s*\([^)]*\)\s*\{{", re.M),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        start = match.end() - 1
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(start, len(text)):
            ch = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue
            if ch in "'\"`":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1:index]
    return None


def classify(attrs: str, text: str) -> tuple[str, str | None, str | None, tuple[str, ...], tuple[str, ...]]:
    onclick = ONCLICK_RE.search(attrs)
    type_match = TYPE_RE.search(attrs)
    button_type = type_match.group("type").casefold() if type_match else "button-default"

    if onclick:
        expr = " ".join(onclick.group("expr").split())
        symbol = expr if IDENT_RE.fullmatch(expr) else None
        if symbol:
            body = extract_function_body(text, symbol)
            if body is not None and any(pattern.search(body) for pattern in STUB_PATTERNS):
                return "STUB", expr, symbol, ("STUB_IMPLEMENTATION",), (
                    "Handler body resolved lexically in the same file; no code was executed.",
                )
            return "WIRED", expr, symbol, (), (
                "Handler symbol is lexically bound; downstream executability is not proven.",
            )
        return "WIRED", expr, None, (), (
            "Inline/dynamic onClick is present; handler identity and downstream effects remain unresolved.",
        )

    if button_type == "submit":
        return "UNRESOLVED", None, None, ("FORM_BINDING_UNRESOLVED",), (
            "Submit behavior may be owned by an ancestor form; this lexical PoC does not infer that binding.",
        )

    if DISABLED_RE.search(attrs):
        return "UNRESOLVED", None, None, ("STATIC_OR_DYNAMIC_DISABLED",), (
            "Disabled controls may be conditionally enabled; source presence alone cannot establish reachability.",
        )

    return "DEAD_SURFACE", None, None, ("GUI_HANDLER_MISSING",), (
        "App-authored button has no onClick and is not explicitly a submit control in this manifestation.",
    )


def audit_file(root: Path, path: Path) -> list[Manifestation]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="strict")
    records: list[Manifestation] = []
    for match in BUTTON_RE.finditer(text):
        attrs = match.group("attrs")
        raw = strip_jsx_label(match.group("body"))
        line = line_for(text, match.start())
        state, expr, symbol, gaps, limitations = classify(attrs, text)
        raw_key = f"{rel}\n{line}\n{match.group(0)}"
        records.append(
            Manifestation(
                manifestation_id="sha256:" + sha256_text(raw_key),
                source_path=rel,
                line=line,
                raw_label=raw,
                normalized_label=normalize_label(raw),
                control_type="jsx_button",
                handler_expression=expr,
                handler_symbol=symbol,
                side_effect_class=SIDE_EFFECT_CLASS,
                evidence_tier="LEXICAL_DISCOVERY",
                final_state=state,
                gap_codes=gaps,
                limitations=limitations,
            )
        )
    return records


def iter_sources(root: Path) -> Iterable[Path]:
    base = root / "server" / "frontend" / "src"
    if not base.exists():
        return []
    return sorted(
        path for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
    )


def git_value(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, text=True,
            capture_output=True,
        ).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def build_ledger(root: Path) -> dict:
    records: list[Manifestation] = []
    for source in iter_sources(root):
        records.extend(audit_file(root, source))
    records.sort(key=lambda item: (item.source_path, item.line, item.manifestation_id))

    ids = [record.manifestation_id for record in records]
    states = Counter(record.final_state for record in records)
    unknown_states = sorted(set(states) - FINAL_STATES)
    duplicate_ids = len(ids) - len(set(ids))
    classified = sum(states.values())
    discovered = len(records)
    invariant_pass = discovered == classified and duplicate_ids == 0 and not unknown_states

    return {
        "schema_version": SCHEMA_VERSION,
        "audit_mode": "STATIC_NO_TARGET_EXECUTION",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot": {
            "repository": git_value(root, "config", "--get", "remote.origin.url"),
            "commit_sha": git_value(root, "rev-parse", "HEAD"),
            "working_tree": "current checkout",
        },
        "scope": {
            "include": ["server/frontend/src/**/*.tsx", "server/frontend/src/**/*.jsx"],
            "exclude": ["third-party generated controls", "runtime-only DOM", "ancestor form semantic inference"],
            "source_taxonomy_is_not_identity": True,
        },
        "capabilities": [asdict(record) for record in records],
        "coverage": {
            "discovered_manifestations": discovered,
            "classified_manifestations": classified,
            "by_final_state": dict(sorted(states.items())),
        },
        "invariants": {
            "arithmetic_closure": discovered == classified,
            "manifestation_id_unique": duplicate_ids == 0,
            "duplicate_manifestation_ids": duplicate_ids,
            "unknown_final_states": unknown_states,
            "pass": invariant_pass,
        },
        "certification": "AUDIT_ONLY" if invariant_pass else "FAIL",
        "limitations": [
            "Lexical/regex discovery is not exhaustive semantic parsing.",
            "WIRED proves an event binding manifestation, not downstream executability.",
            "No application module, handler, API route, pipeline, or domain feature is imported or invoked.",
            "Dynamic controls/listeners may be missed and remain outside the bounded claim.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("audit/executability/gui-capability-ledger.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    ledger = build_ledger(root)
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    coverage = ledger["coverage"]
    print(
        "EXECUTABILITY_AUDIT "
        f"discovered={coverage['discovered_manifestations']} "
        f"classified={coverage['classified_manifestations']} "
        f"status={ledger['certification']} output={output.relative_to(root)}"
    )
    return 0 if ledger["invariants"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
