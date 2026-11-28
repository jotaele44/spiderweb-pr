"""Read-only pilot context and dataset options."""
from fastapi import APIRouter, HTTPException

from spiderweb.geo_sar.context import resolve_context

router = APIRouter(prefix="/geo-sar", tags=["geo-sar"])


@router.get("/context")
def context(bbox: str):
    try:
        return resolve_context([float(part) for part in bbox.split(",")])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
