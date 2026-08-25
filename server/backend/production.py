from __future__ import annotations

from server.backend.main import app
from server.backend.martin_ingress import observability_snapshot, router

app.include_router(router)


@app.get("/health/martin-delivery")
async def martin_delivery_health():
    """Publication-control snapshot; does not probe or authorize unpublished sources."""
    return observability_snapshot()
