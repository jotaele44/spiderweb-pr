"""Desktop configuration for the canonical Spiderweb GIS application."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_TITLE = "Spiderweb"
FRONTEND_DIR = REPO_ROOT / "server" / "frontend" / "dist"
FRONTEND_ENTRY = FRONTEND_DIR / "index.html"
CATALOG_PATH = REPO_ROOT / "configs" / "layer_catalog.yaml"
HEALTH_PATH = "/health"
