"""
PRIIS Backend API
=================
FastAPI orchestration layer for the Puerto Rico Integrated Intelligence System.
Provides REST endpoints for all PRIIS entities (SQLite-backed), SSE streaming
for pipeline jobs and RAG queries, and GeoJSON endpoints for spatial layers.

Start: uvicorn server.backend.main:app --reload --port 8000
(run from the repo root so relative paths resolve correctly)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

log = logging.getLogger("priis.backend")

# ─── Paths ─────────────────────────────────────────────────────────────────────

# main.py lives at server/backend/main.py → root is two levels up
ROOT = Path(__file__).parent.parent.parent
DB_PATH = Path(__file__).parent.parent / "priis.db"
OUTPUT_DIR = ROOT / "outputs"

# Make sibling ingestion package importable for the startup migration hook.
_INGEST_DIR = Path(__file__).parent.parent / "ingestion"
if str(_INGEST_DIR) not in sys.path:
    sys.path.append(str(_INGEST_DIR))

# ─── Startup migrations ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run idempotent SQLite migrations on boot, then yield to request loop.

    Migrations are synchronous (sqlite3) and one-shot — fine to block startup.
    If priis.db doesn't exist yet we skip silently; seed_demo.py will create it
    and apply the schema (which already includes the migrated columns).
    """
    if DB_PATH.exists():
        try:
            from migrations import run_all as run_migrations  # type: ignore
            conn = sqlite3.connect(DB_PATH)
            try:
                result = run_migrations(conn)
                log.info("startup migrations applied: %s", result)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — log and continue serving
            log.warning("startup migrations skipped: %s", exc)
    else:
        log.info("priis.db missing at %s; skipping startup migrations", DB_PATH)
    yield

# ─── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="PRIIS API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job registry: job_id → subprocess.Popen
_jobs: dict = {}

# ─── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json_fields(row: dict, fields: list[str]) -> dict:
    for f in fields:
        if row.get(f):
            try:
                row[f] = json.loads(row[f])
            except (json.JSONDecodeError, TypeError):
                row[f] = []
    return row


def _camel_provenance(row: dict[str, Any]) -> dict[str, Any]:
    _parse_json_fields(row, ["source_ids", "lineage"])
    row["sourceIds"] = row.pop("source_ids", [])
    if "captured_at" in row:
        row["capturedAt"] = row.pop("captured_at", None)
    if "provenance_note" in row:
        row["provenanceNote"] = row.pop("provenance_note", None)
    return row


async def _rows(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        raise HTTPException(
            503,
            "PRIIS database is unavailable; no synthetic records were substituted",
        )
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

# ─── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness + DB integrity (T10-83).

    Reports the DB path/existence and, when the DB is present, runs
    ``PRAGMA integrity_check`` and counts user tables. ``status`` is ``ok`` only
    when the DB exists and integrity passes; ``degraded`` otherwise. Always
    returns 200 so a load balancer can read the body rather than guessing.
    """
    result: dict[str, Any] = {
        "status": "ok",
        "db": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
    }
    if not DB_PATH.exists():
        result["status"] = "degraded"
        result["reason"] = "db_missing"
        return result
    try:
        integrity = (await _rows("PRAGMA integrity_check"))
        ok = bool(integrity) and str(
            next(iter(integrity[0].values()))
        ).lower() == "ok"
        tables = await _rows(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'"
        )
        result["integrity_ok"] = ok
        result["table_count"] = tables[0]["n"] if tables else 0
        if not ok:
            result["status"] = "degraded"
            result["reason"] = "integrity_check_failed"
    except Exception as exc:  # pragma: no cover - defensive
        result["status"] = "degraded"
        result["reason"] = f"db_error: {exc}"
    return result

# ─── Entity endpoints ──────────────────────────────────────────────────────────

@app.get("/agencies")
async def list_agencies():
    return await _rows("SELECT id, code, name FROM agencies")


@app.get("/vendors")
async def list_vendors():
    return await _rows("SELECT id, name, risk, tier FROM vendors")


@app.get("/sites")
async def list_sites():
    rows = await _rows(
        "SELECT id, name, kind, lat, lng, sensitive, infrastructure_class, "
        "municipio_geoid, tract_geoid, zcta_geoid, source_ids, lineage FROM sites"
    )
    for r in rows:
        r["sensitive"] = bool(r["sensitive"])
        _camel_provenance(r)
    return rows


@app.get("/contracts")
async def list_contracts():
    return await _rows(
        "SELECT id, agency, vendor, site, amount, signed, status, tier, note, "
        "procurement_method FROM contracts"
    )


@app.get("/events")
async def list_events():
    rows = await _rows(
        "SELECT id, kind, at, site_id, ref_id, label, tier, "
        "registration, callsign, aircraft_type, operator, origin_code, "
        "destination_code, altitude_ft, ground_speed_mph, flight_status, "
        "image_path, source_ids, lineage FROM events"
    )
    for r in rows:
        _camel_provenance(r)
        r["siteId"] = r.pop("site_id", None)
        r["refId"] = r.pop("ref_id", None)
        r["aircraftType"] = r.pop("aircraft_type", None)
        r["originCode"] = r.pop("origin_code", None)
        r["destinationCode"] = r.pop("destination_code", None)
        r["altitudeFt"] = r.pop("altitude_ft", None)
        r["groundSpeedMph"] = r.pop("ground_speed_mph", None)
        r["flightStatus"] = r.pop("flight_status", None)
        r["imagePath"] = r.pop("image_path", None)
    return rows


@app.get("/events/{flight_id}/track")
async def event_track(flight_id: str):
    """Ordered per-point ADS-B track for a flight event (route playback).

    Returns the position reports ingested by scripts/parse_adsb_archive.py into
    the track_points table, oldest first. Empty list if the flight has no track.
    """
    rows = await _rows(
        "SELECT ts, at, lat, lng, altitude_ft, speed, direction "
        "FROM track_points WHERE flight_id = ? ORDER BY ts",
        (flight_id,),
    )
    for r in rows:
        r["altitudeFt"] = r.pop("altitude_ft", None)
    return rows


@app.get("/anomalies")
async def list_anomalies():
    rows = await _rows(
        "SELECT id, title, category, score, band, site_id, summary, "
        "factors, contracts, event_ids, confidence, contradictions, "
        "source_ids, lineage FROM anomalies"
    )
    for r in rows:
        _camel_provenance(r)
        r["siteId"] = r.pop("site_id", None)
        r["events"] = json.loads(r.pop("event_ids") or "[]")
        _parse_json_fields(r, ["factors", "contracts", "contradictions"])
    return rows


@app.get("/sources")
async def list_sources():
    rows = await _rows(
        "SELECT id, name, tier, kind, status, publisher, url, captured_at, "
        "hash, lineage, provenance_note FROM sources"
    )
    return [_camel_provenance(row) for row in rows]


@app.get("/investigations")
async def list_investigations():
    return await _rows("SELECT id, title, active_vector, status FROM investigations")


@app.get("/alerts")
async def list_alerts():
    return await _rows(
        "SELECT id, at, kind, title, tier, investigation, registration FROM alerts"
    )

# ─── Pipeline ──────────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    phase: Optional[int] = None
    images: Optional[int] = None


@app.post("/pipeline/run")
async def pipeline_run(req: PipelineRunRequest = PipelineRunRequest()):
    job_id = str(uuid.uuid4())
    cmd = ["python", str(ROOT / "run_all.py")]
    if req.phase is not None:
        cmd += ["--phase", str(req.phase)]
    if req.images is not None:
        cmd += ["--images", str(req.images)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ROOT),
    )
    _jobs[job_id] = proc
    return {"job_id": job_id, "status": "running"}


@app.get("/pipeline/status/{job_id}")
async def pipeline_status(job_id: str):
    proc = _jobs.get(job_id)
    if proc is None:
        raise HTTPException(404, "job not found")
    rc = proc.poll()
    if rc is None:
        return {"job_id": job_id, "status": "running"}
    return {"job_id": job_id, "status": "done" if rc == 0 else "error", "returncode": rc}


async def _stream_stdout(proc: subprocess.Popen) -> AsyncGenerator[dict, None]:
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        yield {"data": line.rstrip()}
    yield {"event": "done", "data": json.dumps({"returncode": proc.poll()})}


@app.get("/pipeline/events/{job_id}")
async def pipeline_events(job_id: str):
    proc = _jobs.get(job_id)
    if proc is None:
        raise HTTPException(404, "job not found")
    return EventSourceResponse(_stream_stdout(proc))


@app.delete("/pipeline/{job_id}")
async def pipeline_stop(job_id: str):
    proc = _jobs.get(job_id)
    if proc is None:
        raise HTTPException(404, "job not found")
    proc.terminate()
    _jobs.pop(job_id, None)
    return {"job_id": job_id, "status": "terminated"}

# ─── GeoJSON layers ────────────────────────────────────────────────────────────

# The set of servable layers is derived from the Layer Catalog (single source of
# truth, configs/layer_catalog.yaml, built by scripts/build_layer_catalog.py) so the
# allowlist and the catalogued folder tree can't drift. The hardcoded fallback keeps
# the geo API online if the catalog file is missing or unreadable.
CATALOG_PATH = ROOT / "configs" / "layer_catalog.yaml"
_FALLBACK_LAYERS = {
    # Operational overlays
    "sites", "anomalies", "corridors", "heatmap",
    # PR administrative geographies (TIGER/Line, joined via ingest_tiger_pr.py)
    "municipios", "tracts", "places", "barrios", "puma",
    # PR reference / environmental geographies (via ingest_reference_geo.py)
    "nid_dams", "gazetteer_pr_domestic_names", "wetlands_nwi_prvi",
}


def _load_layer_catalog() -> dict:
    try:
        import yaml
        return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        log.warning("layer_catalog.yaml not found at %s — using fallback allowlist", CATALOG_PATH)
        return {}
    except Exception as exc:  # malformed YAML, etc. — never take the geo API offline
        log.warning("failed to load layer_catalog.yaml (%s) — using fallback allowlist", exc)
        return {}


_LAYER_CATALOG = _load_layer_catalog()
_ALLOWED_LAYERS = {
    layer["layer_id"]
    for fam in _LAYER_CATALOG.get("families", [])
    for layer in fam.get("layers", [])
} or _FALLBACK_LAYERS


def _find_geojson(layer: str) -> Optional[Path]:
    candidates = [
        OUTPUT_DIR / f"{layer}.geojson",
        ROOT / "data" / f"{layer}.geojson",
        ROOT / f"{layer}.geojson",
    ]
    return next((p for p in candidates if p.exists()), None)


@lru_cache(maxsize=64)
def _sha256_file(path: str, mtime_ns: int, size: int) -> str:
    """Hash a stable file identity; mtime/size make the cache self-invalidating."""
    del mtime_ns, size
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(path: Optional[Path]) -> tuple[Optional[str], Optional[str]]:
    if path is None or not path.exists():
        return None, None
    stat = path.stat()
    captured_at = datetime.fromtimestamp(
        stat.st_mtime,
        timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    return _sha256_file(str(path), stat.st_mtime_ns, stat.st_size), captured_at


def _manifest_provenance(layer_id: str) -> dict[str, Any]:
    tiger_layers = {"municipios", "tracts", "places", "barrios", "puma"}
    if layer_id in tiger_layers:
        manifest_path = ROOT / "data" / "tiger" / "2025" / "manifest.json"
    else:
        manifest_path = (
            ROOT / "data" / "reference_geo" / f"{layer_id}_manifest.json"
        )
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read provenance manifest %s: %s", manifest_path, exc)
        return {}

    if "layers" in manifest:
        entry = next(
            (
                candidate
                for candidate in manifest.get("layers", [])
                if candidate.get("layer") == layer_id
            ),
            {},
        )
    elif manifest.get("layer") == layer_id:
        entry = manifest
    else:
        entry = {}
    if not entry:
        return {}

    source = entry.get("source", {})
    output = entry.get("output", {})
    generated_at = manifest.get("generated_utc")
    manifest_rel = str(manifest_path.relative_to(ROOT))
    return {
        "source_ids": [f"catalog:{layer_id}", f"manifest:{manifest_rel}"],
        "url": source.get("url"),
        "captured_at": generated_at,
        "hash": output.get("sha256") or source.get("sha256"),
        "lineage": [
            {
                "actor": manifest.get("ingestor", "unknown"),
                "step": "capture",
                "at": generated_at,
                "source": source.get("filename") or source.get("url"),
            },
            {
                "actor": manifest.get("ingestor", "unknown"),
                "step": "materialize",
                "at": generated_at,
                "output": output.get("path"),
            },
        ],
        "manifest": manifest_rel,
    }


def _layer_provenance(
    layer_id: str,
    geometry_path: Optional[Path],
    geometry_source: str,
) -> dict[str, Any]:
    manifest = _manifest_provenance(layer_id)
    identity_path = geometry_path
    if geometry_source == "sqlite":
        identity_path = DB_PATH
    file_hash, captured_at = _file_identity(identity_path)
    relative_path = None
    if identity_path is not None:
        try:
            relative_path = str(identity_path.relative_to(ROOT))
        except ValueError:
            relative_path = str(identity_path)
    fallback_lineage = [
        {
            "actor": "spiderweb-pr",
            "step": "serve",
            "source": relative_path,
        }
    ]
    return {
        "catalog": "configs/layer_catalog.yaml",
        "geometry_source": geometry_source,
        "source_ids": manifest.get("source_ids", [f"catalog:{layer_id}"]),
        "url": manifest.get("url"),
        "captured_at": manifest.get("captured_at") or captured_at,
        "hash": manifest.get("hash") or file_hash,
        "lineage": manifest.get("lineage") or fallback_lineage,
        "manifest": manifest.get("manifest"),
        "geometry_path": relative_path,
    }


async def _sites_from_db() -> dict:
    rows = await _rows(
        "SELECT id, name, kind, lat, lng, sensitive, infrastructure_class, "
        "source_ids, lineage FROM sites"
    )
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {
                "id": r["id"],
                "name": r["name"],
                "kind": r["kind"],
                "sensitive": bool(r["sensitive"]),
                "infrastructure_class": r.get("infrastructure_class"),
                "source_ids": json.loads(r["source_ids"] or "[]"),
                "lineage": json.loads(r["lineage"] or "[]"),
            },
        }
        for r in rows
        if r.get("lat") is not None and r.get("lng") is not None
    ]
    return {"type": "FeatureCollection", "features": features}


async def _anomalies_from_db() -> dict:
    rows = await _rows(
        "SELECT a.id, a.title, a.score, a.band, a.category, "
        "a.source_ids, a.lineage, s.lat, s.lng "
        "FROM anomalies a LEFT JOIN sites s ON a.site_id = s.id"
    )
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {
                "id": r["id"],
                "title": r["title"],
                "score": r["score"],
                "band": r["band"],
                "source_ids": json.loads(r["source_ids"] or "[]"),
                "lineage": json.loads(r["lineage"] or "[]"),
            },
        }
        for r in rows
        if r.get("lat") is not None and r.get("lng") is not None
    ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/geo/{layer}.geojson")
async def geo_layer(layer: str):
    if layer not in _ALLOWED_LAYERS:
        raise HTTPException(400, f"unknown layer '{layer}'")
    path = _find_geojson(layer)
    if path is not None:
        return FileResponse(str(path), media_type="application/geo+json")
    if layer == "sites":
        if not DB_PATH.exists():
            raise HTTPException(503, "sites geometry unavailable: PRIIS database missing")
        return JSONResponse(await _sites_from_db(), media_type="application/geo+json")
    if layer == "anomalies":
        if not DB_PATH.exists():
            raise HTTPException(
                503, "anomaly geometry unavailable: PRIIS database missing"
            )
        return JSONResponse(await _anomalies_from_db(), media_type="application/geo+json")
    raise HTTPException(
        404,
        f"layer '{layer}' is catalogued but its geometry has not been materialized",
    )


@app.get("/catalog")
async def layer_catalog():
    """Return the catalog enriched with truthful runtime geometry availability."""
    if not _LAYER_CATALOG:
        raise HTTPException(503, "layer catalog unavailable")
    catalog = json.loads(json.dumps(_LAYER_CATALOG))
    database_counts: dict[str, int] = {}
    if DB_PATH.exists():
        for layer, table in (("sites", "sites"), ("anomalies", "anomalies")):
            try:
                rows = await _rows(f"SELECT COUNT(*) AS n FROM {table}")
                database_counts[layer] = rows[0]["n"] if rows else 0
            except Exception as exc:  # noqa: BLE001 - availability remains explicit
                log.warning("could not count %s geometry: %s", layer, exc)

    for family in catalog.get("families", []):
        for layer in family.get("layers", []):
            layer_id = layer["layer_id"]
            path = _find_geojson(layer_id)
            endpoint = f"/geo/{layer_id}.geojson"
            if path is not None:
                runtime_status = "live"
                geometry_source = "exported_geojson"
                feature_count = None
            elif layer_id in database_counts:
                feature_count = database_counts[layer_id]
                runtime_status = "live" if feature_count else "empty"
                geometry_source = "sqlite"
            else:
                runtime_status = (
                    "unavailable" if layer.get("pipeline_wired") else "deferred"
                )
                geometry_source = "not_materialized"
                feature_count = None
            layer.update(
                {
                    "runtime_status": runtime_status,
                    "feature_count": feature_count,
                    "endpoint": endpoint,
                    "provenance": _layer_provenance(
                        layer_id,
                        path,
                        geometry_source,
                    ),
                }
            )
    return catalog

# ─── RAG / Query ───────────────────────────────────────────────────────────────

class RagQueryRequest(BaseModel):
    query: str
    top_k: int = 5
    no_context: bool = False


async def _stream_rag(query: str, top_k: int, no_context: bool) -> AsyncGenerator[dict, None]:
    cmd = ["python", str(ROOT / "query_llm.py"), query, "--top-k", str(top_k)]
    if no_context:
        cmd.append("--no-context")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
    )
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        yield {"data": line.rstrip()}
    rc = proc.wait()
    yield {"event": "done", "data": json.dumps({"returncode": rc})}


@app.post("/rag/query")
async def rag_query(req: RagQueryRequest):
    return EventSourceResponse(_stream_rag(req.query, req.top_k, req.no_context))


@app.post("/rag/index")
async def rag_index():
    job_id = str(uuid.uuid4())
    proc = subprocess.Popen(
        ["python", str(ROOT / "rag_pipeline.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ROOT),
    )
    _jobs[job_id] = proc
    return {"job_id": job_id, "status": "indexing"}
