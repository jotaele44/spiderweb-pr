"""OpenTopography Global DEM API adapter (SRTMGL1, NASADEM, COP30, AW3D30)."""

from .client import build_request_url, load_config, redact

__all__ = ["build_request_url", "load_config", "redact"]
