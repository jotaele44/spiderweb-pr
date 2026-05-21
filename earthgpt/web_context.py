"""
EarthGPT iOS — Web context enrichment.

Optionally fetches supplementary geographic metadata for candidate tiles.
Designed to be tolerant of network failure (returns empty metadata).
"""

import json
from typing import Optional

import requests

from .log_utils import warn


ALLOWED_DOMAINS = {
    "tiles.mapbox.com", "api.mapbox.com", "maps.googleapis.com",
    "earthengine.googleapis.com", "sentinel-hub.com", "copernicus.eu",
}


def validate_url(url: str) -> bool:
    """Reject non-HTTPS and non-whitelisted domain URLs."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    domain = parsed.netloc.lstrip("www.")
    return any(domain.endswith(d) for d in ALLOWED_DOMAINS)


def fetch_nominatim_context(lat: float, lon: float, timeout: int = 8) -> dict:
    """
    Reverse-geocode a lat/lon using Nominatim (OSM).

    Returns a dict with place metadata, or an empty dict on failure.
    No crash on network error.
    """
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "json"}
        headers = {"User-Agent": "EarthGPT-iOS/0.1"}
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "display_name": data.get("display_name", ""),
                "place_type": data.get("type", ""),
                "country": data.get("address", {}).get("country", ""),
            }
    except Exception as exc:
        warn(f"Nominatim lookup failed for ({lat},{lon}): {exc}")
    return {}
