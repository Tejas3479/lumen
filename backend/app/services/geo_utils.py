"""
Lumen Geo Utilities

Haversine distance, proximity checking, reverse geocoding via Nominatim,
ward/zone extraction, and cluster geometry helpers.

Used by:
  Session 4  — auto-fill address + ward on issue creation
  Session 10 — hard verification proximity check (is_within_radius)
  Session 16 — DBSCAN hotspot cluster centres (cluster_centre, cluster_radius)
"""
import math
from typing import Optional

import httpx

from app.config import settings
from app.logging_config import logger


# ── Haversine ─────────────────────────────────────────────────

def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Return the great-circle distance in metres between two GPS points.

    Uses the haversine formula, which gives the shortest distance over
    the Earth's surface and is accurate to within ~0.3% for all distances.

    Args:
        lat1, lon1: First point in decimal degrees.
        lat2, lon2: Second point in decimal degrees.

    Returns:
        Distance in metres as a float.
    """
    R = 6_371_000  # Earth mean radius in metres

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi    = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ── Proximity check ───────────────────────────────────────────

def is_within_radius(
    user_lat: float,
    user_lng: float,
    issue_lat: float,
    issue_lng: float,
    radius_meters: Optional[float] = None,
) -> tuple[bool, float]:
    """
    Check whether a user is within ``radius_meters`` of an issue location.

    Falls back to ``settings.hard_verification_radius_meters`` (default 100 m)
    when ``radius_meters`` is not provided.

    Returns:
        ``(is_within: bool, actual_distance_meters: float)``
    """
    if radius_meters is None:
        radius_meters = settings.hard_verification_radius_meters

    distance = haversine_distance(user_lat, user_lng, issue_lat, issue_lng)
    return distance <= radius_meters, distance


# ── Bounding box ──────────────────────────────────────────────

def bounding_box(
    lat: float,
    lng: float,
    radius_meters: float,
) -> tuple[float, float, float, float]:
    """
    Compute a lat/lng bounding box for a given centre point and radius.

    Used by ``issue_service.get_issues_nearby`` as a cheap SQL pre-filter
    before the exact haversine calculation is applied in Python.

    The longitude delta accounts for the latitude-dependent convergence of
    meridians: degrees of longitude shrink as ``cos(lat)`` toward the poles.

    Returns:
        ``(min_lat, max_lat, min_lng, max_lng)``
    """
    lat_delta = radius_meters / 111_320.0
    lng_delta = radius_meters / (111_320.0 * math.cos(math.radians(lat)))
    return (
        lat - lat_delta,
        lat + lat_delta,
        lng - lng_delta,
        lng + lng_delta,
    )


# ── Reverse geocoding ─────────────────────────────────────────

async def reverse_geocode(lat: float, lng: float) -> dict:
    """
    Converts GPS coordinates to human-readable address.
    Priority:
      1. Google Geocoding API (accurate, handles Indian addresses well)
      2. Nominatim (free fallback, rate-limited to 1 req/sec)
      3. Coordinate string (offline fallback)
    """
    # Try Google Geocoding API first
    if settings.google_api_key:
        result = await _google_geocode(lat, lng)
        if result:
            return result

    # Fall back to Nominatim
    return await _nominatim_geocode(lat, lng)


async def _google_geocode(lat: float, lng: float) -> dict | None:
    """
    Uses Google Geocoding API for reverse geocoding.
    Returns parsed address dict or None on failure.
    Parses Indian address components: ward, zone, city.
    """
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lng}",
        "key": settings.google_api_key,
        "language": "en",
        "result_type": "street_address|sublocality|locality",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return None

        result = data["results"][0]
        components = {c["types"][0]: c["long_name"] for c in result["address_components"]}

        # Extract Indian address hierarchy
        road = components.get("route", "")
        sublocality = (
            components.get("sublocality_level_1")
            or components.get("sublocality", "")
        )
        city = components.get("locality", components.get("administrative_area_level_2", ""))
        state = components.get("administrative_area_level_1", "")
        postcode = components.get("postal_code", "")

        # Build display address
        parts = [p for p in [road, sublocality, city] if p]
        display_address = ", ".join(parts) if parts else result.get("formatted_address", "")[:100]

        logger.info(
            "Google Geocode success",
            extra={"lat": lat, "lng": lng, "address": display_address},
        )

        return {
            "address": display_address,
            "ward": sublocality or None,
            "zone": city or None,
            "city": city,
            "state": state,
            "postcode": postcode,
            "raw": components,
            "source": "google",
        }

    except Exception as e:
        logger.warning("Google Geocode failed", extra={"error": str(e)})
        return None


async def _nominatim_geocode(lat: float, lng: float) -> dict:
    """
    Nominatim reverse geocoding.
    Rate limited to 1 req/sec. Used as fallback.
    """
    url = f"{settings.nominatim_url}/reverse"
    params = {
        "lat": lat, "lon": lng, "format": "jsonv2",
        "zoom": 18, "addressdetails": 1,
    }
    headers = {
        "User-Agent": settings.geocoding_user_agent,
        "Accept-Language": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        address_parts = data.get("address", {})
        road = address_parts.get("road", "")
        neighbourhood = address_parts.get("neighbourhood", "")
        suburb = address_parts.get("suburb", "")
        city_district = address_parts.get("city_district", "")
        city = address_parts.get("city", address_parts.get("town", ""))
        state = address_parts.get("state", "")
        postcode = address_parts.get("postcode", "")

        parts = [p for p in [road, neighbourhood or suburb, city_district or city] if p]
        display_address = ", ".join(parts) if parts else data.get("display_name", "")[:100]
        ward = suburb or neighbourhood or city_district or None

        return {
            "address": display_address,
            "ward": ward,
            "zone": city or None,
            "city": city,
            "state": state,
            "postcode": postcode,
            "raw": address_parts,
            "source": "nominatim",
        }
    except Exception as e:
        logger.warning("Nominatim geocode failed", extra={"error": str(e)})
        return _fallback_geocode(lat, lng)


def _fallback_geocode(lat: float, lng: float) -> dict:
    """
    Return a minimal address dict when Nominatim is unavailable.

    The address field is a human-readable coordinate string so the UI
    always has something to display.
    """
    return {
        "address":  f"Near {lat:.4f}, {lng:.4f}",
        "ward":     None,
        "zone":     None,
        "city":     None,
        "state":    None,
        "postcode": None,
        "raw":      {},
        "source":   "fallback",
    }


# ── Cluster geometry (Session 16) ─────────────────────────────

def cluster_centre(
    coordinates: list[tuple[float, float]],
) -> tuple[float, float]:
    """
    Compute the arithmetic mean centre of a list of (lat, lng) coordinates.

    Used by ``predictive.py`` (Session 16) to find the geographic centre
    of a DBSCAN cluster of civic issues.

    Args:
        coordinates: Non-empty list of ``(latitude, longitude)`` tuples.

    Returns:
        ``(mean_lat, mean_lng)`` tuple.

    Raises:
        ValueError: If ``coordinates`` is empty.

    Note:
        Arithmetic mean is accurate for clusters spanning < ~100 km.
        For global-scale clustering, use spherical mean instead.
    """
    if not coordinates:
        raise ValueError("Cannot compute centre of empty coordinate list")
    n = len(coordinates)
    mean_lat = sum(c[0] for c in coordinates) / n
    mean_lng = sum(c[1] for c in coordinates) / n
    return mean_lat, mean_lng


def cluster_radius(
    centre_lat: float,
    centre_lng: float,
    coordinates: list[tuple[float, float]],
    padding_factor: float = 1.2,
) -> float:
    """
    Return the radius in metres that encompasses all ``coordinates``
    from the given centre point, scaled by ``padding_factor``.

    Used by Session 16's hotspot radius calculation to create a slightly
    larger circle than the tightest bounding radius so edge points are
    clearly inside the hotspot zone on the map.

    Args:
        centre_lat, centre_lng: Cluster centre coordinates.
        coordinates: List of ``(lat, lng)`` tuples in the cluster.
        padding_factor: Multiplier applied to the max distance (default 1.2).

    Returns:
        Padded radius in metres. Returns ``0.0`` for an empty list.
    """
    if not coordinates:
        return 0.0
    max_dist = max(
        haversine_distance(centre_lat, centre_lng, lat, lng)
        for lat, lng in coordinates
    )
    return max_dist * padding_factor
