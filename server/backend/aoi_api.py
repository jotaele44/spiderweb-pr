"""Read-only planning API; acquisition is intentionally not exposed."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .aoi_planner import MAX_BYTES, build_plan, strict_json

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter(prefix="/spatial/aoi", tags=["AOI acquisition planning"])


def load_registry(root: Path) -> dict:
    path = root / "configs" / "spatial_dataset_providers.json"
    try:
        return strict_json(path.read_bytes())
    except (OSError, ValueError):
        # build_plan will explicitly expose a blocked registry, never READY/zero.
        return {}


@router.post("/plan")
async def plan_aoi(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "application/json is required")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "AOI request exceeds 5 MiB")
    try:
        payload = strict_json(bytes(raw))
        registry = await asyncio.to_thread(load_registry, ROOT)
        plan = await asyncio.to_thread(build_plan, payload, registry, ROOT)
    except ImportError as exc:
        raise HTTPException(503, "AOI geometry dependencies unavailable; install [server,geo]") from exc
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(422, f"AOI validation failed: {exc}") from exc
    # Round trip forbids non-JSON numerical states before publishing a frozen plan.
    plan = json.loads(json.dumps(plan, allow_nan=False))
    return JSONResponse(plan, headers={"Cache-Control": "no-store"})
