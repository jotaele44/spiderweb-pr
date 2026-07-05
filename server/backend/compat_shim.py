"""Read-only compatibility API for the migrated Spiderweb frontend."""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

RowsFn = Callable[[str, tuple], Awaitable[list[dict[str, Any]]]]
StreamRagFn = Callable[[str, int, bool], AsyncGenerator[dict, None]]
EMPTY_FC = {"type": "FeatureCollection", "features": []}

ENTITY_SQL = {
    "sites": "SELECT id, name, kind, lat, lng, sensitive, infrastructure_class, municipio_geoid, tract_geoid, zcta_geoid FROM sites",
    "contracts": "SELECT id, agency, vendor, site, amount, signed, status, tier, note, procurement_method FROM contracts",
    "events": "SELECT id, kind, at, site_id, ref_id, label, tier, registration, callsign, aircraft_type, operator, origin_code, destination_code, altitude_ft, ground_speed_mph, flight_status, image_path FROM events",
    "anomalies": "SELECT id, title, category, score, band, site_id, summary, factors, contracts, event_ids, confidence, contradictions FROM anomalies",
    "sources": "SELECT id, name, tier, kind, status FROM sources",
    "investigations": "SELECT id, title, active_vector, status FROM investigations",
    "alerts": "SELECT id, at, kind, title, tier, investigation, registration FROM alerts",
}
ALIASES = {"site_id":"siteId","ref_id":"refId","aircraft_type":"aircraftType","origin_code":"originCode","destination_code":"destinationCode","altitude_ft":"altitudeFt","ground_speed_mph":"groundSpeedMph","flight_status":"flightStatus","image_path":"imagePath"}


def _json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    for old, new in ALIASES.items():
        if old in row:
            row[new] = row.pop(old)
    if "sensitive" in row:
        row["sensitive"] = bool(row["sensitive"])
    if "site_id" in row:
        row["siteId"] = row.pop("site_id")
    if "event_ids" in row:
        row["events"] = _json_list(row.pop("event_ids"))
    for key in ("factors", "contracts", "contradictions"):
        if key in row:
            row[key] = _json_list(row[key])
    return row


async def _read_entity(rows: RowsFn, entity: str) -> list[dict[str, Any]]:
    if entity not in ENTITY_SQL:
        raise HTTPException(404, f"unknown entity '{entity}'")
    try:
        return [_normalize(dict(r)) for r in await rows(ENTITY_SQL[entity], ())]
    except Exception:
        return []


async def _sse_once(message: str) -> AsyncGenerator[dict, None]:
    yield {"data": message}
    yield {"event": "done", "data": json.dumps({"returncode": 0})}


def install_compat_shim(app: FastAPI, rows: RowsFn, stream_rag: StreamRagFn) -> None:
    @app.get("/api/apps/public-settings")
    async def public_settings():
        return {"id":"spiderweb-pr","public_settings":{"requires_auth":False,"mode":"diagnostic","compat_shim":True}}

    @app.get("/api/auth/me")
    async def auth_me():
        return {"id":"anonymous","roles":["read_only"],"diagnostic":True}

    @app.get("/api/entities/{entity}")
    async def entity_list(entity: str, sort: str | None = None, limit: int | None = None):
        data = await _read_entity(rows, entity)
        if sort:
            reverse = sort.startswith("-")
            key = sort[1:] if reverse else sort
            data.sort(key=lambda r: str(r.get(key, "")), reverse=reverse)
        return data[:limit] if limit else data

    @app.post("/api/entities/{entity}/filter")
    async def entity_filter(entity: str, request: Request):
        body = await request.json()
        data = await entity_list(entity, body.get("sort"), None)
        filters = body.get("filters") or {}
        if filters:
            data = [r for r in data if all(r.get(k) == v for k, v in filters.items())]
        limit = body.get("limit")
        return data[:limit] if limit else data

    @app.post("/api/integrations/llm/invoke")
    async def llm_invoke(request: Request):
        payload = await request.json()
        prompt = payload.get("prompt") or payload.get("query") or ""
        result = {"location_name":"Puerto Rico location","municipality":"unknown","region_type":"unknown","elevation_estimate":"unknown","risk_level":"moderate","key_facts":["Diagnostic compatibility response"],"nearby_pois":[],"data_summary":prompt[:240] or "No prompt supplied.","recommendations":["Route this call to /rag/query for live context."]}
        return {"result":json.dumps(result),"diagnostic":True}

    @app.post("/api/files/upload")
    async def files_upload(request: Request):
        filename = "upload"
        try:
            filename = getattr((await request.form()).get("file"), "filename", filename)
        except Exception:
            pass
        return {"filename":filename,"geojson":EMPTY_FC,"diagnostic":True}

    @app.post("/stream/query")
    async def stream_query(request: Request):
        payload = await request.json()
        query = payload.get("question") or payload.get("query") or payload.get("prompt") or json.dumps(payload)
        return EventSourceResponse(stream_rag(query, int(payload.get("top_k") or 5), False))

    @app.post("/stream/analyze-region")
    async def stream_analyze_region(request: Request):
        body = await request.json()
        return EventSourceResponse(_sse_once(f"Diagnostic region analysis: {body.get('question') or 'selected region'}"))

    @app.post("/stream/generate")
    async def stream_generate(request: Request):
        body = await request.json()
        return EventSourceResponse(_sse_once(json.dumps({**EMPTY_FC,"metadata":{"prompt":body.get("prompt"),"diagnostic":True}})))
