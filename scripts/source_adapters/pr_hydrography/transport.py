from __future__ import annotations

import json

TRANSPORT_STATES = {
    "OK",
    "HTTP_REDIRECT",
    "RATE_LIMITED",
    "TIMEOUT",
    "SOURCE_UNAVAILABLE",
    "EMPTY_RESPONSE",
    "UNEXPECTED_HTML",
    "TRUNCATED_JSON",
    "PARTIAL_DOWNLOAD",
    "UNEXPECTED_MEDIA",
}

STEP5A_FAILURE_CLASSES = {
    "SOURCE_UNAVAILABLE",
    "UNEXPECTED_MEDIA",
    "SOURCE_EMPTY",
    "PARTIAL_RESPONSE",
    "REDIRECT_FAILURE",
    "HASH_FAILURE",
    "SCHEMA_CHANGED",
    "UNCLASSIFIED",
}


def classify_transport_outcome(
    *,
    status: int | None,
    content_type: str,
    payload: bytes,
    expected_content: str,
    timed_out: bool = False,
    network_error: bool = False,
    expected_bytes: int | None = None,
) -> str:
    if timed_out:
        return "TIMEOUT"
    if network_error or status is None:
        return "SOURCE_UNAVAILABLE"
    if 300 <= status < 400:
        return "HTTP_REDIRECT"
    if status == 429:
        return "RATE_LIMITED"
    if not payload:
        return "EMPTY_RESPONSE"
    if expected_bytes is not None and len(payload) < expected_bytes:
        return "PARTIAL_DOWNLOAD"

    head = payload[:256].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return "UNEXPECTED_HTML"

    expected = expected_content.lower()
    ctype = (content_type or "").lower()
    if expected in {"json", "geojson", "sciencebase-item-json"}:
        try:
            json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "TRUNCATED_JSON"
        if "json" not in ctype and expected != "geojson":
            return "UNEXPECTED_MEDIA"
    elif expected == "zip":
        if not payload.startswith(b"PK\x03\x04"):
            return "UNEXPECTED_MEDIA"
    return "OK"


def step5a_failure_class(transport_state: str) -> str:
    """Map transport outcomes into the frozen Step 5A failure ontology."""
    mapping = {
        "OK": "",
        "TIMEOUT": "SOURCE_UNAVAILABLE",
        "SOURCE_UNAVAILABLE": "SOURCE_UNAVAILABLE",
        "RATE_LIMITED": "SOURCE_UNAVAILABLE",
        "EMPTY_RESPONSE": "SOURCE_EMPTY",
        "UNEXPECTED_HTML": "UNEXPECTED_MEDIA",
        "UNEXPECTED_MEDIA": "UNEXPECTED_MEDIA",
        "TRUNCATED_JSON": "PARTIAL_RESPONSE",
        "PARTIAL_DOWNLOAD": "PARTIAL_RESPONSE",
        "HTTP_REDIRECT": "REDIRECT_FAILURE",
    }
    return mapping.get(transport_state, "UNCLASSIFIED")


def require_transport_ok(state: str) -> None:
    if state not in TRANSPORT_STATES:
        raise RuntimeError(f"unknown transport state: {state}")
    if state != "OK":
        raise RuntimeError(f"transport not certifiable: {state}")
