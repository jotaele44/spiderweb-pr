"""Dedicated Spiderweb GIS runtime.

The broad PRIIS backend remains available to ingestion and internal tools. The
desktop and canonical frontend use this smaller application so unrelated
tracking, pipeline, alert, and query routes cannot become product surface area.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from server.backend import main

app = FastAPI(
    title="Spiderweb GIS API",
    version="1.0.0",
    lifespan=main.lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_EXCLUDED_EVENT_KINDS = {"flight"}
_EXCLUDED_SOURCE_KINDS = {  # boundary-exclusion: defensive rejection list
    "adsb",
    "aircraft",
    "flight",
    "fr24",  # boundary-exclusion: reject Skywatcher source kind
    "flightradar24",  # boundary-exclusion: reject Skywatcher source kind
}
_AIRCRAFT_FIELDS = {
    "registration",
    "callsign",
    "aircraftType",
    "operator",
    "originCode",
    "destinationCode",
    "altitudeFt",
    "groundSpeedMph",
    "flightStatus",
    "imagePath",
}


def _catalog_is_gis(family: dict[str, Any]) -> bool:
    if family.get("id") == "flight_activity" or family.get("domain") == "flights":
        return False
    family["layers"] = [
        layer
        for layer in family.get("layers", [])
        if layer.get("layer_id") != "flights"
    ]
    return bool(family["layers"])


def _factor_is_excluded(factor: Any) -> bool:
    return isinstance(factor, dict) and factor.get("tag") == "flight"


@app.get("/health")
async def health():
    result = await main.health()
    return {**result, "runtime": "spiderweb-gis"}


@app.get("/sites")
async def sites():
    return await main.list_sites()


@app.get("/events")
async def events():
    records = await main.list_events()
    return [
        {key: value for key, value in record.items() if key not in _AIRCRAFT_FIELDS}
        for record in records
        if record.get("kind") not in _EXCLUDED_EVENT_KINDS
    ]


@app.get("/anomalies")
async def anomalies():
    event_records = await main.list_events()
    excluded_ids = {
        record["id"]
        for record in event_records
        if record.get("kind") in _EXCLUDED_EVENT_KINDS
    }
    records = await main.list_anomalies()
    return [
        record
        for record in records
        if record.get("category") not in _EXCLUDED_EVENT_KINDS
        and not excluded_ids.intersection(record.get("events", []))
        and not any(_factor_is_excluded(factor) for factor in record.get("factors", []))
    ]


@app.get("/sources")
async def sources():
    records = await main.list_sources()
    return [
        record
        for record in records
        if str(record.get("kind", "")).lower() not in _EXCLUDED_SOURCE_KINDS
    ]


@app.get("/catalog")
async def catalog():
    value = await main.layer_catalog()
    value = json.loads(json.dumps(value))
    value["families"] = [
        family for family in value.get("families", []) if _catalog_is_gis(family)
    ]
    return value


@app.get("/geo/{layer}.geojson")
async def geo_layer(layer: str):
    value = await catalog()
    allowed = {
        item["layer_id"]
        for family in value.get("families", [])
        for item in family.get("layers", [])
    }
    if layer not in allowed:
        raise HTTPException(400, f"unknown GIS layer '{layer}'")
    return await main.geo_layer(layer)
