"""
Lumen Predictive Analytics Service
Cluster-based hotspot detection using recent issue history.

Algorithm:
  1. Load all non-closed issues from the last 90 days
  2. Group by geographic grid cell (0.01° ≈ 1 km resolution)
  3. Cells with ≥3 issues become candidate hotspots
  4. For each cluster: compute centroid, radius, dominant category, and confidence
  5. Predict next occurrence date using inter-event time distribution
  6. Write results to predictive_hotspots table
  7. Publish hotspot_update socket event via Redis

Called by: Celery beat task every 6 hours (configured in celery_app.py)
Also called on-demand by the admin dashboard.
"""
import asyncio
import math
import uuid
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

from app.celery_app import celery_app
from app.celery_db import run_with_db
from app.logging_config import logger


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Returns great-circle distance in km between two lat/lon points."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _grid_cell(lat: float, lon: float, resolution: float = 0.01) -> tuple:
    """Quantises lat/lon to a grid cell for clustering."""
    return (round(lat / resolution) * resolution, round(lon / resolution) * resolution)


async def generate_hotspots(db) -> list[dict]:
    """
    Main entry point: generates predictive hotspots from recent issue data.
    Returns list of hotspot dicts that were persisted to the database.

    Steps:
      1. Query issues from last 90 days
      2. Grid-cell clustering (0.01° ≈ 1 km)
      3. Persist clusters with ≥3 issues as PredictiveHotspot records
      4. Return serialised list for socket emission
    """
    from sqlalchemy import select, and_, delete
    from app.models import Issue, PredictiveHotspot

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # Load recent active issues
    result = await db.execute(
        select(Issue.id, Issue.latitude, Issue.longitude,
               Issue.category_id, Issue.created_at, Issue.ward)
        .where(
            and_(
                Issue.created_at >= cutoff,
                Issue.status.notin_(["closed"]),
                Issue.latitude.isnot(None),
                Issue.longitude.isnot(None),
            )
        )
    )
    issues = result.all()

    if not issues:
        logger.info("Predictive hotspot generation: no issues found")
        return []

    # Cluster by category + grid cell
    # Key: (category_id, grid_lat, grid_lon)
    clusters: dict[tuple, list] = defaultdict(list)
    for row in issues:
        cell = _grid_cell(row.latitude, row.longitude)
        key = (row.category_id, cell[0], cell[1])
        clusters[key].append(row)

    # Build hotspot records
    hotspots_data = []
    for (category_id, grid_lat, grid_lon), cluster_issues in clusters.items():
        if len(cluster_issues) < 3:
            continue  # Minimum cluster size

        # Centroid
        center_lat = sum(i.latitude for i in cluster_issues) / len(cluster_issues)
        center_lon = sum(i.longitude for i in cluster_issues) / len(cluster_issues)

        # Radius = max distance from centroid (metres)
        radius_km = max(
            _haversine_km(i.latitude, i.longitude, center_lat, center_lon)
            for i in cluster_issues
        )
        radius_m = max(50.0, radius_km * 1000)

        # Dominant ward
        ward_counts: dict[str, int] = defaultdict(int)
        for i in cluster_issues:
            if i.ward:
                ward_counts[i.ward] += 1
        dominant_ward = max(ward_counts, key=ward_counts.get) if ward_counts else None

        # Category name from first issue (all share same category_id)
        # We'll store category_id for now; the route joins for display
        category_name = str(category_id) if category_id else "unknown"

        # Confidence: based on cluster density and recency
        dates = sorted(i.created_at for i in cluster_issues)
        recency_bonus = 1.0 if dates[-1] >= datetime.now(timezone.utc) - timedelta(days=14) else 0.7
        confidence = min(0.95, (len(cluster_issues) / 20) * recency_bonus)

        # Predict next issue: mean inter-event interval
        if len(dates) >= 2:
            intervals = [
                (dates[i + 1] - dates[i]).total_seconds() / 86400
                for i in range(len(dates) - 1)
            ]
            mean_interval = sum(intervals) / len(intervals)
            predicted_date = (dates[-1] + timedelta(days=mean_interval)).date()
        else:
            predicted_date = None

        hotspots_data.append({
            "category": category_name,
            "center_latitude": round(center_lat, 6),
            "center_longitude": round(center_lon, 6),
            "radius_meters": round(radius_m, 1),
            "issue_count": len(cluster_issues),
            "predicted_next_issue_date": predicted_date,
            "confidence": round(confidence, 3),
            "ward": dominant_ward,
        })

    if not hotspots_data:
        logger.info("Predictive hotspot generation: no clusters met threshold")
        return []

    # Wipe old hotspots and insert new ones
    await db.execute(delete(PredictiveHotspot))

    new_hotspots = []
    for data in hotspots_data:
        h = PredictiveHotspot(
            id=uuid.uuid4(),
            **data,
        )
        db.add(h)
        new_hotspots.append(h)

    await db.flush()

    logger.info(
        "Predictive hotspots generated",
        extra={"count": len(new_hotspots)},
    )

    # Serialise for socket emission
    return [
        {
            "id": str(h.id),
            "category": h.category,
            "center_latitude": h.center_latitude,
            "center_longitude": h.center_longitude,
            "radius_meters": h.radius_meters,
            "issue_count": h.issue_count,
            "predicted_next_issue_date": (
                h.predicted_next_issue_date.isoformat()
                if h.predicted_next_issue_date
                else None
            ),
            "confidence": h.confidence,
            "ward": h.ward,
        }
        for h in new_hotspots
    ]


@celery_app.task(
    name="app.services.predictive.generate_hotspots_task",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def generate_hotspots_task(self):
    """
    Celery beat task: regenerates predictive hotspots every 6 hours.
    Uses the shared Celery engine (one pool per worker process, not per task).
    """
    try:
        from app.utils.async_utils import run_async_task
        hotspots = run_async_task(run_with_db(generate_hotspots))
        logger.info(
            "Hotspot generation task completed",
            extra={"count": len(hotspots)},
        )
        
        # Broadcast updated hotspots via the Socket.IO Redis bridge
        from app.sockets.events import publish_to_socket
        from app.config import settings
        publish_to_socket(settings.redis_url, "hotspot_update", {"hotspots": hotspots})

        return {"status": "ok", "hotspots_generated": len(hotspots)}
    except Exception as exc:
        logger.error(
            "Hotspot generation task failed",
            extra={"error": str(exc), "retry_count": self.request.retries},
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Hotspot generation max retries exceeded")
            return {"status": "failed"}
