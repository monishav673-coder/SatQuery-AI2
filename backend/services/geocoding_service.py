"""
SATQUERY AI — Geocoding Service
Reverse-geocodes (lat, lon) → human-readable place name.

Providers supported:
  1. Nominatim (OpenStreetMap) — free, no key required, default
  2. Google Maps Geocoding API — set GEOCODING_PROVIDER=google and GOOGLE_MAPS_API_KEY in .env

Both paths return a plain string place name, or a fallback if unavailable.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_nominatim_cache: dict = {}


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Return a human-readable place name for the given coordinates.
    Returns None if the geocoding service is unavailable.
    """
    try:
        from flask import current_app
        provider = current_app.config.get("GEOCODING_PROVIDER", "nominatim").lower()
        google_key = current_app.config.get("GOOGLE_MAPS_API_KEY", "")
    except RuntimeError:
        provider = "nominatim"
        google_key = ""

    cache_key = f"{lat:.5f},{lon:.5f}"
    if cache_key in _nominatim_cache:
        return _nominatim_cache[cache_key]

    if provider == "google" and google_key:
        name = _google_reverse(lat, lon, google_key)
    else:
        name = _nominatim_reverse(lat, lon)

    if name:
        _nominatim_cache[cache_key] = name
    return name


def _nominatim_reverse(lat: float, lon: float) -> Optional[str]:
    """
    Nominatim reverse geocoding — free, no API key required.
    Respects the Nominatim usage policy (1 request/second max).
    """
    try:
        import requests
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1,
        }
        headers = {"User-Agent": "SATQUERY-AI/1.0 (satellite-analysis-platform)"}
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        addr = data.get("address", {})
        # Build a concise location string: city/town/village, state, country
        parts = []
        for key in ("city", "town", "village", "suburb", "county", "state", "country"):
            val = addr.get(key)
            if val and val not in parts:
                parts.append(val)
            if len(parts) == 3:
                break
        if parts:
            return ", ".join(parts)
        return data.get("display_name", None)

    except Exception as e:
        logger.warning("Nominatim reverse geocode failed for %.4f,%.4f: %s", lat, lon, e)
        return None


def _google_reverse(lat: float, lon: float, api_key: str) -> Optional[str]:
    """Google Maps Geocoding API reverse geocode."""
    try:
        import requests
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lon}", "key": api_key}
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if results:
            return results[0].get("formatted_address")
        return None
    except Exception as e:
        logger.warning("Google reverse geocode failed: %s", e)
        return None


def forward_geocode(place: str) -> Optional[dict]:
    """
    Forward geocode a place name to (lat, lon).
    Returns {"lat": float, "lon": float, "display": str} or None.
    """
    try:
        import requests
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": place, "format": "json", "limit": 1}
        headers = {"User-Agent": "SATQUERY-AI/1.0 (satellite-analysis-platform)"}
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "display": data[0].get("display_name"),
            }
        return None
    except Exception as e:
        logger.warning("Forward geocode failed for '%s': %s", place, e)
        return None
