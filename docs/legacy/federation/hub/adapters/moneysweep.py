"""moneysweep-pr v1.2.0 package adapter for SpiderWeb PR.

This module intentionally treats moneysweep-pr as an external producer. It
reads a package from disk, validates the v1.2.0 native stream contract, and maps
awards / transactions / entities into SpiderWeb-facing feature artifacts without
importing moneysweep-pr code.

The v1.2.0 on-wire contract (produced by moneysweep-pr's
``scripts/build_export_package.py`` and defined by its
``schemas/moneysweep_*.schema.json``) is the authority for the shapes read
here: a ``files[]`` manifest, dual entity references on money rows
(``recipient_entity_id`` + ``funding_agency_entity_id`` on awards,
``payer_entity_id`` + ``payee_entity_id`` on transactions), and
``location.latitude`` / ``location.longitude`` coordinates. A cross-repo
conformance fixture (``tests/fixtures/moneysweep_v1_2/``) and test guard
against silent contract drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

REQUIRED_STREAMS = {
    "entities",
    "sources",
    "funding_awards",
    "transactions",
    "relationships",
}

EXPECTED_PRODUCER = "moneysweep-pr"
EXPECTED_VERSION = "1.2.0"


class ContractSweeperAdapterError(ValueError):
    """Raised when a moneysweep-pr package cannot be safely consumed."""


@dataclass(frozen=True)
class ContractSweeperPackage:
    """Validated moneysweep-pr package loaded from disk."""

    package_dir: Path
    manifest: dict[str, Any]
    streams: dict[str, list[dict[str, Any]]]

    @property
    def producer(self) -> str:
        return str(self.manifest.get("producer"))

    @property
    def version(self) -> str:
        return str(self.manifest.get("export_contract_version"))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractSweeperAdapterError(f"missing required file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ContractSweeperAdapterError(f"invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractSweeperAdapterError(f"{path.name} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ContractSweeperAdapterError(f"missing required stream: {path.name}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractSweeperAdapterError(f"invalid JSONL in {path.name}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ContractSweeperAdapterError(f"{path.name}:{line_number} must be a JSON object")
        rows.append(row)
    return rows


def _require_text(row: dict[str, Any], field: str, stream: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractSweeperAdapterError(f"{stream} row missing text field: {field}")
    return value


def _optional_text(row: dict[str, Any], field: str) -> str | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ContractSweeperAdapterError(f"field {field} must be text when present")
    return value


def _require_amount(row: dict[str, Any], field: str, stream: str) -> float:
    value = row.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ContractSweeperAdapterError(f"{stream} row missing numeric field: {field}")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0:
        raise ContractSweeperAdapterError(f"{stream} row has invalid amount: {field}")
    return amount


def _validate_date_text(value: str, stream: str, field: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractSweeperAdapterError(f"{stream} row has invalid date {field}: {value}") from exc


def _validate_location(location: Any, stream: str) -> dict[str, Any] | None:
    if location is None:
        return None
    if not isinstance(location, dict):
        raise ContractSweeperAdapterError(f"{stream} row location must be an object")
    lat = location.get("lat")
    lon = location.get("lon")
    if lat is None or lon is None:
        return location
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise ContractSweeperAdapterError(f"{stream} row location lat/lon must be numeric")
    if not (-90 <= float(lat) <= 90) or not (-180 <= float(lon) <= 180):
        raise ContractSweeperAdapterError(f"{stream} row location lat/lon out of range")
    return location


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("producer") != EXPECTED_PRODUCER:
        raise ContractSweeperAdapterError(
            f"unsupported producer {manifest.get('producer')!r}; expected {EXPECTED_PRODUCER!r}"
        )
    if manifest.get("export_contract_version") != EXPECTED_VERSION:
        raise ContractSweeperAdapterError(
            f"unsupported moneysweep-pr export version {manifest.get('export_contract_version')!r}; "
            f"expected {EXPECTED_VERSION!r}"
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ContractSweeperAdapterError("manifest.files must be an array")
    declared_streams = {
        entry.get("stream") for entry in files if isinstance(entry, dict)
    }
    missing = REQUIRED_STREAMS - declared_streams
    if missing:
        raise ContractSweeperAdapterError(f"manifest missing streams: {sorted(missing)}")


def _validate_streams(streams: dict[str, list[dict[str, Any]]], *, mode: str) -> None:
    entities = {_require_text(row, "entity_id", "entities") for row in streams["entities"]}
    sources = {_require_text(row, "source_id", "sources") for row in streams["sources"]}

    for stream_name, rows in streams.items():
        for row in rows:
            if mode == "production" and row.get("synthetic") is True:
                raise ContractSweeperAdapterError(f"synthetic row rejected in production stream {stream_name}")

    for row in streams["entities"]:
        _require_text(row, "normalized_name", "entities")
        external_ids = row.get("external_ids")
        if external_ids is not None and not isinstance(external_ids, dict):
            raise ContractSweeperAdapterError("entities.external_ids must be an object when present")

    for row in streams["funding_awards"]:
        _require_text(row, "award_id", "funding_awards")
        recipient_id = _require_text(row, "recipient_entity_id", "funding_awards")
        if recipient_id not in entities:
            raise ContractSweeperAdapterError(f"funding_awards references unknown recipient_entity_id: {recipient_id}")
        agency_id = _optional_text(row, "funding_agency_entity_id")
        if agency_id and agency_id not in entities:
            raise ContractSweeperAdapterError(f"funding_awards references unknown funding_agency_entity_id: {agency_id}")
        source_id = _optional_text(row, "source_id")
        if source_id and source_id not in sources:
            raise ContractSweeperAdapterError(f"funding_awards references unknown source_id: {source_id}")
        _require_amount(row, "amount", "funding_awards")
        _require_text(row, "currency", "funding_awards")
        award_date = _require_text(row, "award_date", "funding_awards")
        _validate_date_text(award_date, "funding_awards", "award_date")
        _validate_location(row.get("location"), "funding_awards")

    for row in streams["transactions"]:
        _require_text(row, "transaction_id", "transactions")
        payer_id = _require_text(row, "payer_entity_id", "transactions")
        payee_id = _require_text(row, "payee_entity_id", "transactions")
        if payer_id not in entities:
            raise ContractSweeperAdapterError(f"transactions references unknown payer_entity_id: {payer_id}")
        if payee_id not in entities:
            raise ContractSweeperAdapterError(f"transactions references unknown payee_entity_id: {payee_id}")
        source_id = _optional_text(row, "source_id")
        if source_id and source_id not in sources:
            raise ContractSweeperAdapterError(f"transactions references unknown source_id: {source_id}")
        _require_amount(row, "amount", "transactions")
        _require_text(row, "currency", "transactions")
        transaction_date = _require_text(row, "transaction_date", "transactions")
        _validate_date_text(transaction_date, "transactions", "transaction_date")
        _validate_location(row.get("location"), "transactions")

    for row in streams["relationships"]:
        _require_text(row, "relationship_id", "relationships")
        source_entity_id = _require_text(row, "source_entity_id", "relationships")
        target_entity_id = _require_text(row, "target_entity_id", "relationships")
        if source_entity_id not in entities:
            raise ContractSweeperAdapterError(f"relationships references unknown source_entity_id: {source_entity_id}")
        if target_entity_id not in entities:
            raise ContractSweeperAdapterError(f"relationships references unknown target_entity_id: {target_entity_id}")


def load_moneysweep_package(package_dir: str | Path, *, mode: str = "test") -> ContractSweeperPackage:
    """Load and validate a moneysweep-pr v1.2.0 package directory."""

    if mode not in {"test", "production"}:
        raise ContractSweeperAdapterError("mode must be 'test' or 'production'")
    root = Path(package_dir)
    manifest = _load_json(root / "manifest.json")
    _validate_manifest(manifest)
    streams = {name: _load_jsonl(root / f"{name}.jsonl") for name in REQUIRED_STREAMS}
    _validate_streams(streams, mode=mode)
    return ContractSweeperPackage(package_dir=root, manifest=manifest, streams=streams)


def _entity_index(package: ContractSweeperPackage) -> dict[str, dict[str, Any]]:
    return {row["entity_id"]: row for row in package.streams["entities"]}


def _source_index(package: ContractSweeperPackage) -> dict[str, dict[str, Any]]:
    return {row["source_id"]: row for row in package.streams["sources"]}


def location_point(location: Any) -> tuple[float, float] | None:
    """Return ``(lat, lon)`` floats from a v1.2.0 location object, or ``None``.

    Canonical keys are ``latitude``/``longitude``; ``lat``/``lon`` are tolerated
    for resilience. The single source of truth for reading coordinates off a
    moneysweep-pr money row, shared by the adapter and the consumer gate.
    """
    if not isinstance(location, dict):
        return None
    lat = location.get("latitude", location.get("lat"))
    lon = location.get("longitude", location.get("lon"))
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    return None


def _feature_from_money_row(
    row: dict[str, Any],
    entity: dict[str, Any],
    source: dict[str, Any] | None,
    kind: str,
    *,
    primary_ref_field: str,
    counterparty_ref_field: str,
) -> dict[str, Any]:
    location = row.get("location") or {}
    point = location_point(location)
    geometry = (
        {"type": "Point", "coordinates": [point[1], point[0]]} if point else None
    )
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "feature_type": kind,
            "record_id": row.get("award_id") or row.get("transaction_id"),
            "entity_id": row.get(primary_ref_field),
            "counterparty_entity_id": row.get(counterparty_ref_field),
            "entity": {
                "normalized_name": entity.get("normalized_name"),
                # producer ships `name`; older shapes used `raw_name`.
                "raw_name": entity.get("name") or entity.get("raw_name"),
                "external_ids": entity.get("external_ids") or {},
            },
            "amount": row.get("amount"),
            "currency": row.get("currency"),
            "date": row.get("award_date") or row.get("transaction_date"),
            "municipality_code": location.get("municipality_code"),
            "municipality_name": location.get("municipality_name"),
            "source_id": row.get("source_id"),
            "source": source or {},
            "lineage": row.get("lineage") or {},
            "confidence": row.get("confidence"),
            "synthetic": bool(row.get("synthetic", False)),
        },
    }


def _municipality_density(features: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties", {})
        code = props.get("municipality_code") or "UNKNOWN"
        name = props.get("municipality_name") or "UNKNOWN"
        amount = float(props.get("amount") or 0)
        bucket = totals.setdefault(code, {"municipality_code": code, "municipality_name": name, "total_amount": 0.0, "record_count": 0})
        bucket["total_amount"] += amount
        bucket["record_count"] += 1
    return sorted(totals.values(), key=lambda row: (-row["total_amount"], row["municipality_code"]))


def normalize_moneysweep_records(package: ContractSweeperPackage) -> dict[str, Any]:
    """Map moneysweep-pr native streams into SpiderWeb contract/finance features."""

    entities = _entity_index(package)
    sources = _source_index(package)
    awards = [
        _feature_from_money_row(
            row,
            entities[row["recipient_entity_id"]],
            sources.get(row.get("source_id")),
            "contract_award",
            primary_ref_field="recipient_entity_id",
            counterparty_ref_field="funding_agency_entity_id",
        )
        for row in package.streams["funding_awards"]
    ]
    flows = [
        _feature_from_money_row(
            row,
            entities[row["payee_entity_id"]],
            sources.get(row.get("source_id")),
            "financial_flow",
            primary_ref_field="payee_entity_id",
            counterparty_ref_field="payer_entity_id",
        )
        for row in package.streams["transactions"]
    ]
    return {
        "contract_awards": awards,
        "financial_flows": flows,
        "municipality_funding_density": _municipality_density([*awards, *flows]),
        "entity_graph_edges": package.streams["relationships"],
        "entities": package.streams["entities"],
        "sources": package.streams["sources"],
    }


def _write_geojson(path: Path, features: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2, sort_keys=True), encoding="utf-8")


def _write_density_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["municipality_code", "municipality_name", "total_amount", "record_count"])
        writer.writeheader()
        writer.writerows(rows)


def _xml_escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _write_graphml(path: Path, entities: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="relationship_type" for="edge" attr.name="relationship_type" attr.type="string"/>',
        '  <graph id="moneysweep_entities" edgedefault="directed">',
    ]
    for entity in entities:
        entity_id = _xml_escape(entity.get("entity_id"))
        label = _xml_escape(entity.get("normalized_name", entity_id))
        lines.extend([
            f'    <node id="{entity_id}">',
            f'      <data key="label">{label}</data>',
            '    </node>',
        ])
    for edge in edges:
        edge_id = _xml_escape(edge.get("relationship_id"))
        source = _xml_escape(edge.get("source_entity_id"))
        target = _xml_escape(edge.get("target_entity_id"))
        relationship_type = _xml_escape(edge.get("relationship_type", "related"))
        lines.extend([
            f'    <edge id="{edge_id}" source="{source}" target="{target}">',
            f'      <data key="relationship_type">{relationship_type}</data>',
            '    </edge>',
        ])
    lines.extend(['  </graph>', '</graphml>', ''])
    path.write_text("\n".join(lines), encoding="utf-8")


def export_moneysweep_features(package_dir: str | Path, out_dir: str | Path, *, mode: str = "test") -> dict[str, Any]:
    """Load, validate, normalize, and export SpiderWeb contract/finance artifacts."""

    package = load_moneysweep_package(package_dir, mode=mode)
    normalized = normalize_moneysweep_records(package)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    _write_geojson(out / "contract_awards.geojson", normalized["contract_awards"])
    _write_geojson(out / "financial_flows.geojson", normalized["financial_flows"])
    _write_density_csv(out / "municipality_funding_density.csv", normalized["municipality_funding_density"])
    _write_graphml(out / "entity_graph.graphml", normalized["entities"], normalized["entity_graph_edges"])

    report = {
        "producer": package.producer,
        "export_contract_version": package.version,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_package": str(package.package_dir),
        "outputs": {
            "contract_awards_geojson": "contract_awards.geojson",
            "financial_flows_geojson": "financial_flows.geojson",
            "municipality_funding_density_csv": "municipality_funding_density.csv",
            "entity_graph_graphml": "entity_graph.graphml",
        },
        "counts": {
            "entities": len(normalized["entities"]),
            "sources": len(normalized["sources"]),
            "contract_awards": len(normalized["contract_awards"]),
            "financial_flows": len(normalized["financial_flows"]),
            "entity_graph_edges": len(normalized["entity_graph_edges"]),
            "municipality_funding_density": len(normalized["municipality_funding_density"]),
        },
    }
    (out / "contract_finance_ingest_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
