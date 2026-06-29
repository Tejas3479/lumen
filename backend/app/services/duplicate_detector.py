"""
Lumen Duplicate Detector

Identifies potential duplicate issues using a two-stage pipeline:
  1. Geo-radius pre-filter (fast SQL bounding box + Haversine refinement)
  2. Sentence-transformer cosine similarity on title + description

Why two stages:
  - Stage 1 (geo) is O(1) with DB indexes — runs in < 5ms
  - Stage 2 (embeddings) is O(n) where n = geo candidates — typically < 5 issues
  - Combined: precise deduplication without full-table embedding scans

Similarity thresholds:
  - Below 0.65: different issues, submit normally
  - 0.65–0.84:  possible duplicate — show panel with warning
  - 0.85+:      likely duplicate  — strong recommendation to support existing

Radius: 150 metres
  - Potholes on the same road 200m apart are different infrastructure problems.
  - 150m means: same block, same junction, or same short road segment.

Fallback:
  - If sentence-transformers can't load, uses Jaccard word-overlap similarity.
  - Duplicate checking never blocks submission — failures return empty list.
"""
import math
import asyncio
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Issue, Category
from app.services.geo_utils import haversine_distance, bounding_box
from app.logging_config import logger

# ── Configuration constants ──────────────────────────────────
DUPLICATE_RADIUS_METERS: float = 150.0
SIMILARITY_THRESHOLD_WARNING: float = 0.65   # Show warning panel
SIMILARITY_THRESHOLD_LIKELY: float = 0.85    # Strong "likely duplicate" label

# ── Embedding model singleton ────────────────────────────────
# Loaded once on first call and cached in module-level memory.
# Model: all-MiniLM-L6-v2 — ~80MB, fast inference, strong semantic similarity.
# Falls back gracefully to Jaccard if the model cannot be loaded.
_embedding_model = None
_model_lock = asyncio.Lock()


async def _get_embedding_model():
    """
    Lazily loads the SentenceTransformer model in a thread pool executor
    (model loading is a blocking I/O + compute operation).
    Thread-safe via asyncio.Lock — only one coroutine loads the model.
    Returns None if model cannot be loaded (Jaccard fallback activates).
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    async with _model_lock:
        # Double-check after acquiring lock (another coroutine may have loaded it)
        if _embedding_model is not None:
            return _embedding_model
        try:
            from sentence_transformers import SentenceTransformer

            def _load():
                return SentenceTransformer("all-MiniLM-L6-v2")

            loop = asyncio.get_event_loop()
            _embedding_model = await loop.run_in_executor(None, _load)
            logger.info("Sentence transformer model loaded for duplicate detection")
        except Exception as e:
            logger.warning(
                "Could not load sentence transformer model",
                extra={"error": str(e)},
            )
            _embedding_model = None

    return _embedding_model


def _cosine_similarity(vec_a: list, vec_b: list) -> float:
    """
    Computes cosine similarity between two embedding vectors.
    Returns a value in [-1, 1]; for semantic text embeddings, typically [0, 1].

    Args:
        vec_a, vec_b: Equal-length lists of floats (embedding vectors).

    Returns:
        Cosine similarity score, or 0.0 if either vector is the zero vector.
    """
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    Fallback word-overlap similarity when embedding model is unavailable.
    Jaccard: |intersection| / |union| of word sets.

    Lower than embedding similarity for near-paraphrase detection, but zero-cost
    and always available. Threshold adjustments should account for this.

    Returns:
        Jaccard similarity in [0, 1].
    """
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


async def _get_gemini_embeddings(texts: list[str]) -> list[list[float]] | None:
    """
    Uses Google's gemini-embedding-001 model for semantic similarity.
    Returns list of embedding vectors, or None if unavailable.
    gemini-embedding-001 produces vectors optimised for English
    and Indian-language text — better than all-MiniLM-L6-v2 for
    Bengaluru civic descriptions.
    """
    api_key = settings.google_api_key or settings.gemini_api_key
    if not api_key:
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-embedding-001:batchEmbedContents?key={api_key}"
    )

    requests = [
        {"model": "models/gemini-embedding-001", "content": {"parts": [{"text": t}]}}
        for t in texts
    ]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"requests": requests})
            response.raise_for_status()
            data = response.json()
            return [
                item["values"]
                for item in data.get("embeddings", [])
            ]
    except Exception as e:
        logger.warning("Gemini embeddings failed", error=str(e))
        return None


async def _compute_similarity(text_a: str, text_b: str) -> float:
    """
    Computes semantic similarity.
    Priority: Gemini gemini-embedding-001 → sentence-transformers → Jaccard fallback.
    """
    # Try Gemini embeddings first (Google Technologies)
    embeddings = await _get_gemini_embeddings([text_a, text_b])
    if embeddings and len(embeddings) == 2:
        return float(_cosine_similarity(embeddings[0], embeddings[1]))

    # Fallback to local sentence-transformers
    model = await _get_embedding_model()
    if model is not None:
        try:
            def _embed(texts):
                return model.encode(texts, show_progress_bar=False)
            import asyncio
            embs = await asyncio.get_event_loop().run_in_executor(None, _embed, [text_a, text_b])
            return float(_cosine_similarity(embs[0].tolist(), embs[1].tolist()))
        except Exception:
            pass

    # Jaccard word-overlap fallback
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


async def find_duplicates(
    title: str,
    description: str,
    latitude: float,
    longitude: float,
    category_id: Optional[object],
    db: AsyncSession,
    limit: int = 3,
) -> list[dict]:
    """
    Finds potential duplicate issues for a new civic report.

    Four-stage pipeline:
      1. SQL bounding-box pre-filter (fast, uses lat/lng DB indexes)
      2. Haversine refinement to exact radius (eliminates bounding-box corners)
      3. Category match score boost (same category = ×1.2, capped at 1.0)
      4. Text similarity scoring via sentence-transformer or Jaccard fallback

    Args:
        title:       Issue title from the submit form.
        description: Issue description from the submit form.
        latitude:    GPS latitude of the new report.
        longitude:   GPS longitude of the new report.
        category_id: UUID of the selected category (optional).
        db:          Async SQLAlchemy session.
        limit:       Maximum number of duplicates to return (default: 3).

    Returns:
        List of dicts, sorted by similarity_score desc then distance_meters asc.
        Each dict contains:
            issue_id, title, status, latitude, longitude, address,
            vote_count, verification_count, category,
            distance_meters, similarity_score, duplicate_strength ('possible'|'likely')
        Returns empty list [] if no candidates meet the threshold.
    """
    # ── Stage 1: SQL bounding-box pre-filter ─────────────
    min_lat, max_lat, min_lng, max_lng = bounding_box(
        latitude, longitude, DUPLICATE_RADIUS_METERS
    )

    query = (
        select(Issue)
        .options(selectinload(Issue.category))
        .where(
            and_(
                Issue.latitude.between(min_lat, max_lat),
                Issue.longitude.between(min_lng, max_lng),
                # Only check open issues — closed/resolved issues shouldn't
                # prevent new submissions for recurring infrastructure problems
                Issue.status.notin_(["closed", "resolved"]),
            )
        )
        .limit(20)  # Cap pre-filter to avoid worst-case O(n) embeddings
    )

    result = await db.execute(query)
    candidates = result.scalars().all()

    if not candidates:
        return []

    logger.info(
        "Duplicate check bounding-box candidates",
        extra={
            "count": len(candidates),
            "radius": DUPLICATE_RADIUS_METERS,
        }
    )

    # ── Stage 2: Haversine refinement ────────────────────
    # Bounding box is rectangular, but our radius is circular.
    # Haversine filters out the corners.
    geo_filtered: list[tuple[Issue, float]] = []
    for candidate in candidates:
        dist = haversine_distance(
            latitude, longitude,
            candidate.latitude, candidate.longitude,
        )
        if dist <= DUPLICATE_RADIUS_METERS:
            geo_filtered.append((candidate, dist))

    if not geo_filtered:
        return []

    # ── Stage 3 + 4: Category bonus + text similarity ────
    combined_text = f"{title} {description}".strip()
    scored: list[dict] = []

    for candidate, distance in geo_filtered:
        candidate_text = f"{candidate.title} {candidate.description}".strip()
        similarity = await _compute_similarity(combined_text, candidate_text)

        # Apply category match bonus: same category → multiply by 1.2 (capped at 1.0)
        # Different or unknown category → no change (×1.0)
        # Rationale: "water_leakage" and "drainage" 50m apart may be the same event,
        # so we don't exclude cross-category matches — we just boost same-category ones.
        if category_id and candidate.category_id and candidate.category_id == category_id:
            similarity = min(1.0, similarity * 1.2)

        if similarity >= SIMILARITY_THRESHOLD_WARNING:
            strength = (
                "likely" if similarity >= SIMILARITY_THRESHOLD_LIKELY else "possible"
            )
            scored.append({
                "issue_id": str(candidate.id),
                "title": candidate.title,
                "status": candidate.status,
                "latitude": candidate.latitude,
                "longitude": candidate.longitude,
                "address": candidate.address,
                "vote_count": candidate.vote_count,
                "verification_count": candidate.verification_count,
                "category": (
                    candidate.category.display_name if candidate.category else None
                ),
                "distance_meters": round(distance, 1),
                "similarity_score": round(similarity, 3),
                "duplicate_strength": strength,
            })

    # Sort: highest similarity first; break ties by closest distance
    scored.sort(key=lambda x: (-x["similarity_score"], x["distance_meters"]))
    result_list = scored[:limit]

    if result_list:
        logger.info(
            "Duplicate candidates found",
            extra={
                "count": len(result_list),
                "top_similarity": result_list[0]["similarity_score"],
                "top_distance_m": result_list[0]["distance_meters"],
            }
        )
    else:
        logger.info("No duplicate candidates above threshold")

    return result_list
