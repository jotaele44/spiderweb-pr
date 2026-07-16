"""On-demand Census Partnership Puerto Rico shapefile downloader.

Runtime payloads are written only to policy-approved local paths. Small ledgers
and manifests can be reviewed and promoted separately.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:  # pragma: no cover - supports direct script execution and package imports
    from .parse_form import (
        MAX_BATCH_SIZE,
        CensusPartnershipForm,
        MunicipioOption,
        make_batches,
        parse_partnership_form,
        select_municipios,
    )
except ImportError:  # pragma: no cover
    from parse_form import (  # type: ignore
        MAX_BATCH_SIZE,
        CensusPartnershipForm,
        MunicipioOption,
        make_batches,
        parse_partnership_form,
        select_municipios,
    )

DEFAULT_SOURCE_URL = "https://www.census.gov/geo/partnerships/pvs/partnership25v2/st72_pr.html"
DEFAULT_RUNTIME_ROOT = Path("data/raw/census_partnership_pr")
DEFAULT_MANIFEST_ROOT = Path("manifests/census_partnership_pr")
ZIP_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class DownloadRecord:
    batch_id: str
    requested_municipios: str
    source_url: str
    form_action: str
    request_method: str
    request_params: str
    download_timestamp_utc: str
    http_status: int | str
    content_type: str
    filename: str
    sha256: str
    bytes: int
    extract_status: str
    normalized_output_path: str
    review_status: str
    error: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def is_zip_payload(payload: bytes, content_type: str = "") -> bool:
    """Return true when the payload is plausibly a ZIP archive."""

    lowered = (content_type or "").lower()
    if payload.startswith(ZIP_MAGIC):
        return True
    if payload[:128].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return False
    return "zip" in lowered and not payload[:128].lstrip().lower().startswith(b"<")


def fetch_html(url: str, timeout: int = 60) -> str:
    req = Request(url, headers={"User-Agent": "spiderweb-pr-census-adapter/1.0"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - controlled user-requested public URL
        return response.read().decode("utf-8", errors="replace")


def build_request_params(form: CensusPartnershipForm, batch: Iterable[MunicipioOption]) -> list[tuple[str, str]]:
    params = list(form.hidden_fields)
    params.extend((option.input_name, option.input_value) for option in batch)
    return params


def download_batch(
    form: CensusPartnershipForm,
    batch: tuple[MunicipioOption, ...],
    runtime_root: Path,
    timeout: int = 120,
) -> DownloadRecord:
    codes = tuple(option.code for option in batch)
    batch_id = "pr72_" + "_".join(codes)
    timestamp = utc_now()
    params = build_request_params(form, batch)
    encoded = urlencode(params).encode("utf-8")
    request_params_json = json.dumps(params, ensure_ascii=False)
    runtime_root.mkdir(parents=True, exist_ok=True)
    filename = runtime_root / f"{batch_id}.zip"

    method = form.method.upper()
    if method == "POST":
        req = Request(
            form.action_url,
            data=encoded,
            headers={
                "User-Agent": "spiderweb-pr-census-adapter/1.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
    else:
        separator = "&" if "?" in form.action_url else "?"
        req = Request(
            form.action_url + separator + encoded.decode("utf-8"),
            headers={"User-Agent": "spiderweb-pr-census-adapter/1.0"},
            method="GET",
        )

    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310 - controlled public Census URL
            payload = response.read()
            status = getattr(response, "status", "")
            content_type = response.headers.get("Content-Type", "")
    except (HTTPError, URLError, TimeoutError) as exc:
        return _failed_record(batch_id, codes, form, method, request_params_json, timestamp, filename, exc)

    digest = sha256_bytes(payload)
    if not is_zip_payload(payload, content_type):
        hold_path = filename.with_suffix(".response.html")
        hold_path.write_bytes(payload)
        return DownloadRecord(
            batch_id=batch_id,
            requested_municipios=";".join(codes),
            source_url=form.source_url,
            form_action=form.action_url,
            request_method=method,
            request_params=request_params_json,
            download_timestamp_utc=timestamp,
            http_status=status,
            content_type=content_type,
            filename=str(hold_path),
            sha256=digest,
            bytes=len(payload),
            extract_status="not_extracted",
            normalized_output_path="",
            review_status="hold",
            error="response_not_zip",
        )

    filename.write_bytes(payload)
    return DownloadRecord(
        batch_id=batch_id,
        requested_municipios=";".join(codes),
        source_url=form.source_url,
        form_action=form.action_url,
        request_method=method,
        request_params=request_params_json,
        download_timestamp_utc=timestamp,
        http_status=status,
        content_type=content_type,
        filename=str(filename),
        sha256=digest,
        bytes=len(payload),
        extract_status="not_extracted",
        normalized_output_path="",
        review_status="raw",
        error="",
    )


def _failed_record(
    batch_id: str,
    codes: tuple[str, ...],
    form: CensusPartnershipForm,
    method: str,
    request_params_json: str,
    timestamp: str,
    filename: Path,
    exc: BaseException,
) -> DownloadRecord:
    return DownloadRecord(
        batch_id=batch_id,
        requested_municipios=";".join(codes),
        source_url=form.source_url,
        form_action=form.action_url,
        request_method=method,
        request_params=request_params_json,
        download_timestamp_utc=timestamp,
        http_status=getattr(exc, "code", ""),
        content_type="",
        filename=str(filename),
        sha256="",
        bytes=0,
        extract_status="not_extracted",
        normalized_output_path="",
        review_status="failed",
        error=str(exc),
    )


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_municipio_universe(path: Path, form: CensusPartnershipForm) -> None:
    write_csv(
        path,
        (asdict(option) for option in form.municipios),
        ["code", "name", "input_name", "input_value"],
    )


def write_source_manifest(path: Path, form: CensusPartnershipForm) -> None:
    write_csv(
        path,
        [
            {
                "source_url": form.source_url,
                "form_action": form.action_url,
                "request_method": form.method.upper(),
                "hidden_field_count": len(form.hidden_fields),
                "municipio_count": len(form.municipios),
                "parsed_timestamp_utc": utc_now(),
            }
        ],
        [
            "source_url",
            "form_action",
            "request_method",
            "hidden_field_count",
            "municipio_count",
            "parsed_timestamp_utc",
        ],
    )


def write_download_ledgers(manifest_root: Path, records: list[DownloadRecord]) -> None:
    rows = [asdict(record) for record in records]
    fields = list(DownloadRecord.__dataclass_fields__.keys())
    write_csv(manifest_root / "download_ledger.csv", rows, fields)
    write_csv(
        manifest_root / "sha256_manifest.csv",
        [
            {
                "batch_id": record.batch_id,
                "filename": record.filename,
                "sha256": record.sha256,
                "bytes": record.bytes,
                "review_status": record.review_status,
            }
            for record in records
        ],
        ["batch_id", "filename", "sha256", "bytes", "review_status"],
    )


def write_coverage_ledger(path: Path, expected: int, selected: int, records: list[DownloadRecord]) -> None:
    acquired = sum(1 for record in records if record.review_status in {"raw", "validated", "promoted"})
    failed = sum(1 for record in records if record.review_status == "failed")
    hold = sum(1 for record in records if record.review_status == "hold")
    batch_count = len(records)
    coverage_pct = round((acquired / batch_count) * 100, 2) if batch_count else 0.0
    write_csv(
        path,
        [
            {
                "expected_municipios": expected,
                "selected_municipios": selected,
                "batch_count": batch_count,
                "acquired_batches": acquired,
                "failed_batches": failed,
                "hold_batches": hold,
                "skipped_batches": 0,
                "unresolved_batches": failed + hold,
                "coverage_pct": coverage_pct,
                "generated_timestamp_utc": utc_now(),
            }
        ],
        [
            "expected_municipios",
            "selected_municipios",
            "batch_count",
            "acquired_batches",
            "failed_batches",
            "hold_batches",
            "skipped_batches",
            "unresolved_batches",
            "coverage_pct",
            "generated_timestamp_utc",
        ],
    )


def parse_code_arg(raw: str | None) -> tuple[str, ...] | None:
    if raw is None or raw.strip().lower() in {"", "all"}:
        return None
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def run(args: argparse.Namespace) -> int:
    html = fetch_html(args.source_url, timeout=args.timeout)
    form = parse_partnership_form(html, args.source_url)
    selected = select_municipios(form, parse_code_arg(args.municipios))
    batches = make_batches((option.code for option in selected), batch_size=args.batch_size)
    selected_by_code = {option.code: option for option in selected}

    manifest_root = Path(args.manifest_root)
    runtime_root = Path(args.runtime_root)
    write_source_manifest(manifest_root / "source_manifest.csv", form)
    write_municipio_universe(manifest_root / "municipio_universe.csv", form)

    planned = [";".join(batch) for batch in batches]
    if args.dry_run:
        write_csv(
            manifest_root / "planned_batches.csv",
            ({"batch_id": f"pr72_{'_'.join(batch)}", "municipios": ";".join(batch)} for batch in batches),
            ["batch_id", "municipios"],
        )
        print(json.dumps({"municipios": len(form.municipios), "selected": len(selected), "planned_batches": planned}, indent=2))
        return 0

    records: list[DownloadRecord] = []
    for batch_codes in batches:
        batch_options = tuple(selected_by_code[code] for code in batch_codes)
        records.append(download_batch(form, batch_options, runtime_root, timeout=args.timeout))

    write_download_ledgers(manifest_root, records)
    write_coverage_ledger(manifest_root / "coverage_ledger.csv", len(form.municipios), len(selected), records)
    return 1 if any(record.review_status in {"failed", "hold"} for record in records) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Puerto Rico Census Partnership shapefiles on demand")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--municipios", default="all", help="Comma-separated PR municipio codes or 'all'")
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH_SIZE)
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
