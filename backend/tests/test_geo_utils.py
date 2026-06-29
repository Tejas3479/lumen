"""
Tests: Geo Utility Functions (Session 6)

Covers:
  - haversine_distance: same point, known distance, symmetry
  - is_within_radius: inside, outside
  - bounding_box: shape, 1km span
  - cluster_centre: single, multiple, empty raises ValueError
  - cluster_radius: padded radius
  - _fallback_geocode: output shape
  - reverse_geocode: fallback on network error (monkeypatched)
"""
import math
import pytest
import httpx

from app.services.geo_utils import (
    haversine_distance,
    is_within_radius,
    bounding_box,
    cluster_centre,
    cluster_radius,
    _fallback_geocode,
    reverse_geocode,
)


# ── haversine_distance ────────────────────────────────────────

def test_haversine_same_point():
    """Distance between a point and itself must be exactly 0."""
    d = haversine_distance(12.9716, 77.5946, 12.9716, 77.5946)
    assert d == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    """
    Bengaluru centre to a point ~1 km north.
    0.009° of latitude ≈ 1002 m at equatorial latitudes.
    """
    lat1, lng1 = 12.9716, 77.5946
    lat2, lng2 = 12.9806, 77.5946   # ~1 km north
    d = haversine_distance(lat1, lng1, lat2, lng2)
    assert 950 < d < 1050, f"Expected ~1000 m, got {d:.1f} m"


def test_haversine_symmetry():
    """d(A, B) must equal d(B, A) to floating-point precision."""
    d1 = haversine_distance(12.9, 77.6, 12.95, 77.65)
    d2 = haversine_distance(12.95, 77.65, 12.9, 77.6)
    assert d1 == pytest.approx(d2, rel=1e-9)


def test_haversine_non_negative():
    """Distance must always be ≥ 0."""
    d = haversine_distance(0.0, 0.0, -1.0, -1.0)
    assert d >= 0.0


def test_haversine_equator_poles():
    """Quarter-globe distance should be approximately πR/2 ≈ 10 018 km."""
    # North Pole (90°N) to equator (0°N) same longitude
    d = haversine_distance(90.0, 0.0, 0.0, 0.0)
    assert 10_000_000 < d < 10_100_000, f"Got {d:.0f} m"


# ── is_within_radius ──────────────────────────────────────────

def test_is_within_radius_inside():
    """A point ~50 m away must pass a 100 m radius check."""
    user_lat = 12.9716 + (50 / 111_320)  # ~50 m north
    within, dist = is_within_radius(user_lat, 77.5946, 12.9716, 77.5946, 100.0)
    assert within is True
    assert dist == pytest.approx(50.0, rel=0.05)   # within 5 %


def test_is_within_radius_outside():
    """A point ~500 m away must fail a 100 m radius check."""
    user_lat = 12.9716 + (500 / 111_320)   # ~500 m north
    within, dist = is_within_radius(user_lat, 77.5946, 12.9716, 77.5946, 100.0)
    assert within is False
    assert dist > 100.0


def test_is_within_radius_uses_default(monkeypatch):
    """When radius_meters is omitted, settings.hard_verification_radius_meters is used."""
    from app.services import geo_utils as gu
    monkeypatch.setattr(gu.settings, "hard_verification_radius_meters", 200.0)

    # Point exactly 150 m north — should be within 200 m default
    user_lat = 12.9716 + (150 / 111_320)
    within, _ = gu.is_within_radius(user_lat, 77.5946, 12.9716, 77.5946)
    assert within is True


# ── bounding_box ──────────────────────────────────────────────

def test_bounding_box_shape():
    """Bounding box returns 4 floats: (min_lat, max_lat, min_lng, max_lng)."""
    result = bounding_box(12.9716, 77.5946, 1000.0)
    assert len(result) == 4
    min_lat, max_lat, min_lng, max_lng = result
    assert min_lat < 12.9716 < max_lat
    assert min_lng < 77.5946 < max_lng


def test_bounding_box_1km_radius():
    """
    A 1 km bounding box should span roughly 0.018° of latitude
    (1000 m / 111 320 m/° ≈ 0.009°, total span = 2× = 0.018°).
    """
    min_lat, max_lat, _, _ = bounding_box(12.9716, 77.5946, 1000.0)
    lat_span = max_lat - min_lat
    # Allow 10 % tolerance
    assert 0.016 < lat_span < 0.020, f"lat span = {lat_span:.4f}°"


def test_bounding_box_contains_centre():
    """Centre point must lie strictly inside the bounding box."""
    lat, lng = 28.6139, 77.2090   # New Delhi
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, 500.0)
    assert min_lat < lat < max_lat
    assert min_lng < lng < max_lng


# ── cluster_centre ────────────────────────────────────────────

def test_cluster_centre_single():
    lat, lng = cluster_centre([(12.9716, 77.5946)])
    assert lat == pytest.approx(12.9716)
    assert lng == pytest.approx(77.5946)


def test_cluster_centre_multiple():
    coords = [(10.0, 20.0), (12.0, 22.0), (11.0, 21.0)]
    lat, lng = cluster_centre(coords)
    assert lat == pytest.approx(11.0)
    assert lng == pytest.approx(21.0)


def test_cluster_centre_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        cluster_centre([])


# ── cluster_radius ────────────────────────────────────────────

def test_cluster_radius_with_padding():
    centre_lat, centre_lng = 12.9716, 77.5946
    coords = [
        (12.9716 + (200 / 111_320), 77.5946),  # ~200 m north
        (12.9716 - (100 / 111_320), 77.5946),  # ~100 m south
    ]
    radius = cluster_radius(centre_lat, centre_lng, coords, padding_factor=1.2)
    # Max dist ≈ 200 m; padded = 240 m
    assert 220 < radius < 260, f"Expected ~240 m, got {radius:.1f} m"


def test_cluster_radius_empty():
    assert cluster_radius(0.0, 0.0, []) == 0.0


# ── _fallback_geocode ─────────────────────────────────────────

def test_fallback_geocode_shape():
    result = _fallback_geocode(12.9716, 77.5946)
    for key in ("address", "ward", "zone", "city", "state", "postcode", "raw"):
        assert key in result


def test_fallback_geocode_address_contains_coords():
    result = _fallback_geocode(12.9716, 77.5946)
    assert "12.9716" in result["address"]
    assert result["ward"] is None
    assert result["raw"] == {}


# ── reverse_geocode ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_reverse_geocode_fallback_on_timeout(monkeypatch):
    """When Nominatim times out, fallback dict must be returned without raising."""
    async def mock_get(self, *args, **kwargs):
        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    result = await reverse_geocode(12.9716, 77.5946)
    assert "address" in result
    assert "12.9716" in result["address"]   # fallback uses coords


@pytest.mark.asyncio
async def test_reverse_geocode_fallback_on_http_error(monkeypatch):
    """On HTTP 500, fallback dict must be returned without raising."""
    class FakeResponse:
        status_code = 500
        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "500",
                request=None,
                response=self,
            )

    async def mock_get(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    result = await reverse_geocode(12.9716, 77.5946)
    assert "address" in result
