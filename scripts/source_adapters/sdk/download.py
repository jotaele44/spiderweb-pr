"""Generic HTTP download engine for source adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import DownloadResult, PayloadRequest
from .manifest import utc_now

ZIP_MAGIC = b"PK\x03\x04"


class PayloadValidator:
    """Small content validators for common government payload responses."""

    @staticmethod
    def sha256_bytes(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def looks_like_html(payload: bytes) -> bool:
        head = payload[:256].lstrip().lower()
        return head.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))

    @staticmethod
    def is_zip(payload: bytes, content_type: str = "") -> bool:
        if payload.startswith(ZIP_MAGIC):
            return True
        return "zip" in (content_type or "").lower() and not PayloadValidator.looks_like_html(payload)

    @staticmethod
    def matches_expected(payload: bytes, content_type: str, expected: str) -> bool:
        expected = (expected or "").lower()
        if not expected:
            return not PayloadValidator.looks_like_html(payload)
        if expected == "zip":
            return PayloadValidator.is_zip(payload, content_type)
        if expected == "json":
            return "json" in (content_type or "").lower() and not PayloadValidator.looks_like_html(payload)
        if expected == "csv":
            return "csv" in (content_type or "").lower() or not PayloadValidator.looks_like_html(payload)
        return expected in (content_type or "").lower() and not PayloadValidator.looks_like_html(payload)


class DownloadEngine:
    """Execute deterministic HTTP GET/POST requests and write local payloads."""

    def __init__(self, runtime_root: Path, timeout: int = 120) -> None:
        self.runtime_root = Path(runtime_root)
        self.timeout = timeout

    def download(self, payload_request: PayloadRequest) -> DownloadResult:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        timestamp = utc_now()
        method = payload_request.endpoint.method.upper()
        param_pairs = payload_request.param_pairs()
        encoded_text = urlencode(param_pairs, doseq=True)
        encoded = encoded_text.encode("utf-8")
        # Store the exact ordered pairs used for the request. A JSON object would
        # collapse duplicate keys and could disagree with the submitted payload.
        request_params_json = json.dumps(param_pairs, ensure_ascii=False)
        filename = self.runtime_root / self._filename(payload_request)

        if method == "POST":
            req = Request(
                payload_request.endpoint.url,
                data=encoded,
                headers={"User-Agent": "spiderweb-pr-source-adapter/1.0", **dict(payload_request.headers)},
                method="POST",
            )
        else:
            separator = "&" if "?" in payload_request.endpoint.url else "?"
            url = payload_request.endpoint.url + (separator + encoded_text if encoded_text else "")
            req = Request(url, headers={"User-Agent": "spiderweb-pr-source-adapter/1.0", **dict(payload_request.headers)}, method="GET")

        try:
            with urlopen(req, timeout=self.timeout) as response:  # noqa: S310 - adapters call declared public sources
                payload = response.read()
                status = getattr(response, "status", "")
                content_type = response.headers.get("Content-Type", "")
        except (HTTPError, URLError, TimeoutError) as exc:
            return self._result(payload_request, method, request_params_json, timestamp, filename, "", 0, "", getattr(exc, "code", ""), "failed", str(exc))

        digest = PayloadValidator.sha256_bytes(payload)
        if not PayloadValidator.matches_expected(payload, content_type, payload_request.expected_content):
            hold_path = filename.with_suffix(filename.suffix + ".hold")
            hold_path.write_bytes(payload)
            return self._result(payload_request, method, request_params_json, timestamp, hold_path, digest, len(payload), content_type, status, "hold", "unexpected_payload_type")

        filename.write_bytes(payload)
        return self._result(payload_request, method, request_params_json, timestamp, filename, digest, len(payload), content_type, status, "raw", "")

    def _filename(self, payload_request: PayloadRequest) -> str:
        suffix = ".zip" if payload_request.expected_content.lower() == "zip" else ".payload"
        safe_id = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in payload_request.request_id)
        return f"{safe_id}{suffix}"

    def _result(
        self,
        payload_request: PayloadRequest,
        method: str,
        request_params_json: str,
        timestamp: str,
        filename: Path,
        sha256: str,
        byte_count: int,
        content_type: str,
        status: int | str,
        review_status: str,
        error: str,
    ) -> DownloadResult:
        return DownloadResult(
            request_id=payload_request.request_id,
            source_id=payload_request.endpoint.source_id,
            source_url=payload_request.endpoint.url,
            request_method=method,
            request_params=request_params_json,
            download_timestamp_utc=timestamp,
            http_status=status,
            content_type=content_type,
            filename=str(filename),
            sha256=sha256,
            bytes=byte_count,
            review_status=review_status,
            error=error,
        )
