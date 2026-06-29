"""
Lumen Weekly Ward Report Agent
Generates plain-language ward reports from structured issue data.
Demonstrates: LLM data narration, structured data → narrative generation.

Report format:
  - Headline: 1 sentence summary of the week
  - Narrative: 3-4 paragraph civic journalism report
  - Key achievements: list of resolved issues with impact
  - Key concerns: list of unresolved or newly opened issues
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from app.celery_app import celery_app
from app.config import settings
from app.logging_config import logger


async def _generate_ward_narrative(ward: str, stats: dict) -> dict:
    """
    Calls Gemini to generate a plain-language narrative from ward statistics.
    Returns {headline, narrative, key_achievements, key_concerns}.
    """
    api_key = settings.google_api_key or settings.gemini_api_key
    if not api_key:
        return _generate_fallback_narrative(ward, stats)

    prompt = f"""You are a civic journalist writing a weekly infrastructure report for {ward}, Bengaluru.

Write a factual, plain-language report based on this week's data. Write for residents, not officials.
Be specific about numbers. Be honest about both progress and failures.

WARD DATA — {ward} — Week of {stats.get('week_label', 'this week')}:

Issues reported this week: {stats.get('new_issues', 0)}
Issues resolved this week: {stats.get('resolved_issues', 0)}
Total open issues: {stats.get('open_issues', 0)}
Average resolution time: {stats.get('avg_resolution_days', 'N/A')} days
Most common issue type: {stats.get('top_category', 'unknown')}
Emergency issues: {stats.get('emergency_issues', 0)}
Community verifications: {stats.get('total_verifications', 0)}
Category breakdown: {json.dumps(stats.get('by_category', {}), indent=2)}

Generate a JSON response with these exact fields:
{{
  "headline": "<One engaging sentence summarising this week for {ward}>",
  "narrative": "<3 paragraphs: (1) overall summary, (2) what was fixed, (3) what still needs attention>",
  "key_achievements": ["<achievement 1>", "<achievement 2>", "<achievement 3 if applicable>"],
  "key_concerns": ["<concern 1>", "<concern 2>", "<concern 3 if applicable>"]
}}

Write in plain English. Avoid jargon. Be factual."""

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.5-flash:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 1024,
                "temperature": 0.4,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        raw = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        result = json.loads(raw)
        return {
            "headline": result.get("headline", f"{ward} weekly infrastructure report"),
            "narrative": result.get("narrative", ""),
            "key_achievements": result.get("key_achievements", [])[:5],
            "key_concerns": result.get("key_concerns", [])[:5],
        }

    except Exception as e:
        logger.warning("Ward report generation failed", extra={"ward": ward, "error": str(e)})
        return _generate_fallback_narrative(ward, stats)


def _generate_fallback_narrative(ward: str, stats: dict) -> dict:
    """Rule-based fallback when Gemini is unavailable."""
    new = stats.get("new_issues", 0)
    resolved = stats.get("resolved_issues", 0)
    open_count = stats.get("open_issues", 0)
    top_cat = stats.get("top_category", "infrastructure").replace("_", " ")

    return {
        "headline": (
            f"{ward} saw {new} new issue reports this week, "
            f"with {resolved} resolved."
        ),
        "narrative": (
            f"This week in {ward}, the community reported {new} infrastructure issues "
            f"and {resolved} were resolved. The most common concern was {top_cat}. "
            f"There are currently {open_count} open issues awaiting attention."
        ),
        "key_achievements": [f"{resolved} issues resolved this week"] if resolved else [],
        "key_concerns": [f"{open_count} issues still open"] if open_count else [],
    }


async def _generate_all_ward_reports():
    """
    Generates reports for all wards with activity in the past week.
    """
    from app.celery_db import get_celery_session
    from app.models import Issue, WardReport, Category
    from sqlalchemy import select, func, and_, desc

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    week_end = now

    async with get_celery_session() as db:
        # Find wards with activity this week
        ward_result = await db.execute(
            select(Issue.ward, func.count(Issue.id).label("count"))
            .where(
                Issue.ward.isnot(None),
                Issue.created_at >= week_start,
            )
            .group_by(Issue.ward)
            .order_by(desc("count"))
            .limit(20)  # Top 20 most active wards
        )
        active_wards = [(row[0], row[1]) for row in ward_result.all()]

        if not active_wards:
            logger.info("Ward report agent: no active wards this week")
            return {"generated": 0}

        generated = 0
        for ward, _ in active_wards:
            try:
                # Gather ward statistics
                new_result = await db.execute(
                    select(func.count(Issue.id)).where(
                        Issue.ward == ward,
                        Issue.created_at >= week_start,
                    )
                )
                new_issues = new_result.scalar_one()

                resolved_result = await db.execute(
                    select(func.count(Issue.id)).where(
                        Issue.ward == ward,
                        Issue.status == "resolved",
                        Issue.resolved_at >= week_start,
                    )
                )
                resolved_issues = resolved_result.scalar_one()

                open_result = await db.execute(
                    select(func.count(Issue.id)).where(
                        Issue.ward == ward,
                        Issue.status.notin_(["resolved", "closed"]),
                    )
                )
                open_issues = open_result.scalar_one()

                emergency_result = await db.execute(
                    select(func.count(Issue.id)).where(
                        Issue.ward == ward,
                        Issue.is_emergency == True,
                        Issue.created_at >= week_start,
                    )
                )
                emergency_issues = emergency_result.scalar_one()

                # Category breakdown
                cat_result = await db.execute(
                    select(Issue.ai_category, func.count(Issue.id))
                    .where(Issue.ward == ward, Issue.created_at >= week_start)
                    .group_by(Issue.ai_category)
                    .order_by(desc(func.count(Issue.id)))
                )
                by_category = {row[0] or "other": row[1] for row in cat_result.all()}
                top_category = max(by_category, key=by_category.get) if by_category else "other"

                # Real average resolution time for this ward (last 90 days)
                from sqlalchemy import text as sa_text
                avg_days_result = await db.execute(
                    sa_text(
                        """
                        SELECT AVG(
                            EXTRACT(EPOCH FROM (resolved_at - created_at)) / 86400.0
                        )
                        FROM issues
                        WHERE ward = :ward
                          AND status = 'resolved'
                          AND resolved_at IS NOT NULL
                          AND created_at >= NOW() - INTERVAL '90 days'
                        """
                    ),
                    {"ward": ward}
                )
                avg_resolution_days_raw = avg_days_result.scalar_one()
                avg_resolution_days = round(avg_resolution_days_raw, 1) if avg_resolution_days_raw else None
                avg_days_display = f"{avg_resolution_days} days" if avg_resolution_days else "data pending"

                stats = {
                    "week_label": week_start.strftime("%B %d"),
                    "new_issues": new_issues,
                    "resolved_issues": resolved_issues,
                    "open_issues": open_issues,
                    "emergency_issues": emergency_issues,
                    "by_category": by_category,
                    "top_category": top_category,
                    "avg_resolution_days": avg_days_display,  # Real value or "data pending"
                    "avg_resolution_days_numeric": avg_resolution_days,  # For numeric comparisons
                }

                # Generate narrative
                narrative_data = await _generate_ward_narrative(ward, stats)

                # Save report
                report = WardReport(
                    ward=ward,
                    week_start=week_start,
                    week_end=week_end,
                    stats=stats,
                    headline=narrative_data["headline"],
                    narrative=narrative_data["narrative"],
                    key_achievements=narrative_data["key_achievements"],
                    key_concerns=narrative_data["key_concerns"],
                    agent_model="gemini-3.5-flash",
                )
                db.add(report)
                generated += 1

                logger.info("Ward report generated", extra={"ward": ward})

            except Exception as e:
                logger.error("Ward report failed", extra={"ward": ward, "error": str(e)})

        await db.commit()
        return {"generated": generated, "wards": [w for w, _ in active_wards[:generated]]}


@celery_app.task(name="app.services.ward_report_agent.generate_weekly_reports")
def generate_weekly_reports():
    """
    Celery task: Weekly Ward Report Agent.
    Runs every Monday at 8 AM via Celery Beat.
    Generates plain-language narrative reports for all active wards.
    """
    try:
        result = asyncio.run(_generate_all_ward_reports())
        logger.info("Ward report agent complete", extra=result)
        return result
    except Exception as exc:
        logger.error("Ward report agent failed", extra={"error": str(exc)})
        return {"error": str(exc)}
