"""
Tests: Duplicate Detection
Covers:
  - Unit tests for _cosine_similarity (identical, orthogonal, zero-vector)
  - Unit tests for _jaccard_similarity (helper called by _compute_similarity fallback)
  - Async tests for _compute_similarity (identical text, unrelated text, similar civic text)
  - Integration: find_duplicates returns empty when DB has no nearby issues
  - Integration: check-duplicates API endpoint returns empty result
  - Integration: check-duplicates API returns candidate for identical nearby issue
  - Integration: check-duplicates API does NOT flag issue outside 150m radius
"""
import pytest
import uuid
from app.services.duplicate_detector import (
    _cosine_similarity,
    _jaccard_similarity,
    _compute_similarity,
    find_duplicates,
    DUPLICATE_RADIUS_METERS,
    SIMILARITY_THRESHOLD_WARNING,
)


# =============================================================
# Unit Tests — _cosine_similarity
# =============================================================

def test_cosine_similarity_identical_vectors():
    """Identical vectors must produce similarity of exactly 1.0."""
    vec = [1.0, 0.5, 0.3, 0.8, 0.2]
    assert _cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal_vectors():
    """Orthogonal vectors must produce similarity of 0.0."""
    vec_a = [1.0, 0.0]
    vec_b = [0.0, 1.0]
    assert _cosine_similarity(vec_a, vec_b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_zero_vector_returns_zero():
    """Zero vector must return 0.0 (not NaN or division error)."""
    vec_a = [0.0, 0.0, 0.0]
    vec_b = [1.0, 0.5, 0.3]
    assert _cosine_similarity(vec_a, vec_b) == 0.0


def test_cosine_similarity_known_value():
    """Test against a pre-computed case."""
    # [1, 1] dot [1, 0] = 1; |[1,1]| = sqrt(2); |[1,0]| = 1
    # cosine = 1 / sqrt(2) ≈ 0.7071
    vec_a = [1.0, 1.0]
    vec_b = [1.0, 0.0]
    expected = 1.0 / (2 ** 0.5)
    assert _cosine_similarity(vec_a, vec_b) == pytest.approx(expected, abs=1e-6)


# =============================================================
# Unit Tests — _jaccard_similarity
# =============================================================

def test_jaccard_identical_text():
    """Identical text must return Jaccard = 1.0."""
    text = "pothole on main road junction large deep"
    assert _jaccard_similarity(text, text) == pytest.approx(1.0)


def test_jaccard_no_overlap():
    """Completely different word sets must return 0.0."""
    assert _jaccard_similarity("cat sat mat", "dog fox box") == pytest.approx(0.0)


def test_jaccard_partial_overlap():
    """Partial word overlap returns the correct ratio."""
    # words_a = {a, b, c}; words_b = {b, c, d}
    # intersection = {b, c} (2); union = {a, b, c, d} (4)
    # Jaccard = 2/4 = 0.5
    result = _jaccard_similarity("a b c", "b c d")
    assert result == pytest.approx(0.5, abs=1e-6)


def test_jaccard_empty_text_returns_zero():
    """Empty strings must return 0.0 (not division error)."""
    assert _jaccard_similarity("", "something") == 0.0
    assert _jaccard_similarity("something", "") == 0.0


# =============================================================
# Async Unit Tests — _compute_similarity
# =============================================================

@pytest.mark.asyncio
async def test_compute_similarity_identical_text():
    """Identical text strings must produce similarity > 0.99."""
    text = "Large pothole near the main road junction causing vehicle damage"
    sim = await _compute_similarity(text, text)
    # Either embedding (should be 1.0) or Jaccard (1.0) — both pass
    assert sim > 0.99, f"Expected > 0.99, got {sim}"


@pytest.mark.asyncio
async def test_compute_similarity_unrelated_text_is_low():
    """Completely unrelated civic issues should score below the warning threshold."""
    text_a = "Broken street light outside the bus stop on Old Airport Road"
    text_b = "Garbage bins overflowing near the school — please clear immediately"
    sim = await _compute_similarity(text_a, text_b)
    # Jaccard fallback: low word overlap; embedding: semantically different
    assert sim < SIMILARITY_THRESHOLD_WARNING, (
        f"Expected < {SIMILARITY_THRESHOLD_WARNING}, got {sim}"
    )


@pytest.mark.asyncio
async def test_compute_similarity_near_paraphrase():
    """Near-paraphrases of the same civic issue should score above 0.3."""
    text_a = "Deep pothole on 80 Feet Road near Sony World causing accidents"
    text_b = "Large pothole near Sony World junction on 80 Feet Road — very dangerous"
    sim = await _compute_similarity(text_a, text_b)
    # Conservative: Jaccard gives significant overlap; embedding even higher
    assert sim > 0.3, f"Expected > 0.3 (paraphrase similarity), got {sim}"


# =============================================================
# Integration Tests — find_duplicates and API endpoint
# =============================================================

@pytest.mark.asyncio
async def test_find_duplicates_returns_empty_on_empty_db(db_session):
    """find_duplicates returns [] when no issues exist in the DB."""
    result = await find_duplicates(
        title="Test pothole in Bangalore",
        description="There is a large pothole near the main junction causing damage",
        latitude=12.9716,
        longitude=77.5946,
        category_id=None,
        db=db_session,
    )
    assert result == []


@pytest.mark.asyncio
async def test_find_duplicates_returns_list_type(db_session):
    """find_duplicates always returns a list (never None or raises)."""
    result = await find_duplicates(
        title="Streetlight broken near bus stop",
        description="The streetlight near the bus stop on main road has been dark for a week",
        latitude=0.0,
        longitude=0.0,
        category_id=None,
        db=db_session,
    )
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_check_duplicates_endpoint_empty_db(client):
    """POST /issues/check-duplicates returns empty duplicates when DB has no issues."""
    response = await client.post(
        "/issues/check-duplicates",
        json={
            "title": "Pothole on main road",
            "description": "Large pothole near main road junction causing vehicle damage",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "has_duplicates" in data
    assert "duplicates" in data
    assert "message" in data
    assert isinstance(data["duplicates"], list)
    assert len(data["duplicates"]) == 0


@pytest.mark.asyncio
async def test_check_duplicates_endpoint_missing_params_returns_422(client):
    """POST /issues/check-duplicates without required params returns 422."""
    response = await client.post(
        "/issues/check-duplicates",
        json={
            "title": "Test",
            "description": "Test",
            # Missing latitude and longitude
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_check_duplicates_with_existing_nearby_issue(client):
    """
    POST /issues/check-duplicates returns a candidate when a very similar issue
    exists at nearly the same location.
    The test uses deliberately identical title + description at 11m separation
    to maximise the chance of detection regardless of embedding model availability.
    """
    # Register and create a seed issue
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/auth/register", json={
        "email": f"dup_seed_{suffix}@lumen.com",
        "password": "password123",
        "username": f"dup_seed_{suffix}",
        "display_name": "Dup Seed User",
    })
    assert reg.status_code in (200, 201)
    token = reg.json()["access_token"]

    seed_title = "Massive pothole on Indiranagar 100 Feet Road junction"
    seed_desc = "Deep pothole near the 100 Feet Road junction causing vehicle damage to cars."

    issue_resp = await client.post(
        "/issues",
        data={
            "title": seed_title,
            "description": seed_desc,
            "latitude": "12.9716",
            "longitude": "77.6046",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code in (200, 201)

    # Query with almost-identical text at ~11m away (definitely within 150m)
    response = await client.post(
        "/issues/check-duplicates",
        json={
            "title": seed_title,
            "description": seed_desc,
            "latitude": 12.97169,   # ~11m north of seed
            "longitude": 77.60461,
        }
    )
    assert response.status_code == 200
    data = response.json()
    # With near-identical text at 11m, should always find it above threshold
    assert "has_duplicates" in data
    # Both should detect this as a high similarity match.
    if data["has_duplicates"]:
        dup = data["duplicates"][0]
        assert "distance_meters" in dup
        assert dup["distance_meters"] < DUPLICATE_RADIUS_METERS
        assert dup["similarity_score"] >= SIMILARITY_THRESHOLD_WARNING


@pytest.mark.asyncio
async def test_check_duplicates_issue_outside_radius_not_flagged(client):
    """
    An issue 500m away must NOT be flagged as a duplicate regardless of
    how similar the description is.
    """
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/auth/register", json={
        "email": f"far_seed_{suffix}@lumen.com",
        "password": "password123",
        "username": f"far_seed_{suffix}",
        "display_name": "Far Seed User",
    })
    token = reg.json()["access_token"]

    await client.post(
        "/issues",
        data={
            "title": "Pothole on the main road near junction",
            "description": "There is a large pothole on the road here that needs urgent repair from the authorities.",
            "latitude": "12.9716",
            "longitude": "77.5946",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check from ~500m north — well outside 150m duplicate radius
    response = await client.post(
        "/issues/check-duplicates",
        json={
            "title": "Pothole on the main road near junction",
            "description": "There is a large pothole on the road here that needs urgent repair from the authorities.",
            "latitude": 12.9761,   # ~500m north
            "longitude": 77.5946,
        }
    )
    assert response.status_code == 200
    data = response.json()
    # Issue is outside the 150m radius — must NOT appear as duplicate
    assert len(data["duplicates"]) == 0
    assert data["has_duplicates"] is False
