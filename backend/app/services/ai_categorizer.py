"""
Lumen AI Categorizer
Celery task that calls Google Gemini (primary) or OpenAI GPT-4o (fallback)
to categorize civic issues from images and text descriptions.

Pipeline:
  1. Load image from disk as base64 (if available)
  2. Build prompt for civic issue classification
  3. Call Google Gemini → parse JSON response
  4. Fallback to OpenAI GPT-4o on Gemini error
  5. Fallback to default result if both APIs fail
  6. Update issue record in DB
  7. Emit ai_result WebSocket event via Redis key
  8. Log feedback hooks for RLHF-lite pipeline

Response contract (JSON returned by AI):
{
  "category": "pothole",          // one of the 6 categories
  "severity": "high",             // low | medium | high | critical
  "confidence": 0.91,             // 0.0–1.0
  "explanation": "...",           // 1 sentence, plain language
  "summary": "...",               // ≤ 10 words
  "is_emergency": false           // boolean
}
"""
import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Optional

import httpx
from app.celery_db import get_celery_session
from sqlalchemy import select

from app.celery_app import celery_app
from app.config import settings
from app.logging_config import logger


# ── Prompt engineering ────────────────────────────────────
SYSTEM_PROMPT = """You are a civic infrastructure analyst for an Indian city (Bengaluru).
Your job is to classify community-reported infrastructure issues from photos and descriptions.

=== STEP-BY-STEP REASONING (REQUIRED) ===
Before outputting JSON, think step by step:
1. What do I observe in the image or description?
2. Which category best fits what I observe?
3. What severity indicators are present (size, risk, affected population)?
4. Are there any emergency indicators (accidents, immediate danger, service loss)?
5. How confident am I, and what is the next-best category?

=== CATEGORIES (use ONLY these exact values) ===
- pothole          → road surface damage: cracks, depressions, exposed sub-base
- water_leakage    → pipe bursts, active leaks, water on road from pipes, waterlogging from pipes
- streetlight      → non-functional, broken, or structurally damaged street lights
- garbage          → uncollected waste, illegal dumping, overflowing municipal bins
- drainage         → blocked storm drains, stormwater flooding, uncovered/missing manholes
- other            → footpath damage, faded road markings, fallen trees, other infrastructure

=== SEVERITY (use ONLY these exact values) ===
- low      → minor inconvenience, no immediate safety risk
- medium   → affects daily life, moderate urgency
- high     → safety risk or affects many people, respond within 48 hours
- critical → immediate safety risk, life-threatening, accidents occurring — respond within 2 hours

=== FEW-SHOT EXAMPLES ===

Example 1:
Image shows: cracked asphalt with a 30cm depression in a lane, vehicles swerving
Description: "Pothole on 80 Feet Road near Sony World Signal"
Correct output:
{"reasoning": "I observe broken asphalt with visible sub-base exposure approximately 30cm in diameter. \
This is a road surface failure (pothole). Vehicles are swerving which indicates a safety risk. \
I considered 'other' (road damage) but 'pothole' is the specific category. High severity due to accident risk.",
 "category": "pothole", "severity": "high", "confidence": 0.93,
 "explanation": "Image shows road surface depression with exposed aggregate. Vehicle swerving indicates active safety risk.",
 "summary": "Large pothole causing swerving",
 "alternative_categories": {"other": 0.06, "drainage": 0.01},
 "is_emergency": false}

Example 2:
Image shows: water gushing from a broken pipe joint at road surface level, road flooded
Description: "Water is gushing from pipe near 5th Cross HSR Layout"
Correct output:
{"reasoning": "Water ejection from pipe joint visible at high pressure. This is an active pipe burst, \
not stormwater. Category is water_leakage. Road is flooded so medium-to-high severity. \
No accident reported but road is impassable — high severity.",
 "category": "water_leakage", "severity": "high", "confidence": 0.96,
 "explanation": "Active pipe burst with high-pressure water ejection. Road flooding causing obstruction.",
 "summary": "Active water pipe burst flooding road",
 "alternative_categories": {"drainage": 0.03, "other": 0.01},
 "is_emergency": false}

Example 3:
Image shows: open manhole with no cover on a busy road, traffic visible
Description: "Manhole cover missing on 1st Main Road. Car already fell in."
Correct output:
{"reasoning": "Uncovered manhole on active road — immediate vehicle and pedestrian danger. \
Category is drainage (manhole/stormwater infrastructure). A vehicle has already fallen in — \
this is critical severity and emergency. I am very confident.",
 "category": "drainage", "severity": "critical", "confidence": 0.99,
 "explanation": "Missing manhole cover on busy road with confirmed vehicle accident. Immediate barricading required.",
 "summary": "Missing manhole cover, vehicle fell in",
 "alternative_categories": {"other": 0.01},
 "is_emergency": true}

=== RESPONSE FORMAT ===
Respond ONLY with valid JSON. No markdown. No preamble. No text outside the JSON object.
Required fields: reasoning, category, severity, confidence, explanation, summary, alternative_categories, is_emergency

reasoning: Your step-by-step thought process (2-4 sentences, plain language for citizens to read)
category: One of the six categories above (exact string)
severity: One of the four levels above (exact string)
confidence: Float 0.0–1.0
explanation: One sentence describing what you detected (plain language, no technical jargon)
summary: 5-8 words maximum describing the issue
alternative_categories: Object with up to 2 alternative category names and their confidence scores
is_emergency: Boolean"""


def _build_user_message(description: str, image_base64: Optional[str]) -> list:
    """
    Builds the OpenAI messages content array.
    When an image is present, prepends it as an image_url part using low detail
    (sufficient for civic classification and cheaper to process).
    """
    content = []

    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
                "detail": "low",  # Low detail = faster + cheaper. Sufficient for civic classification.
            },
        })

    content.append({
        "type": "text",
        "text": f"Issue description: {description}\n\nClassify this civic infrastructure issue.",
    })

    return content


def _parse_ai_response(raw: str) -> dict:
    """
    Parses the AI JSON response including new reasoning and alternatives fields.
    Handles cases where the model wraps JSON in markdown code fences.
    Falls back to default values on parse failure.

    Returns a dict with keys: category, severity, confidence,
    explanation, summary, reasoning, alternative_categories, is_emergency.
    """
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner_lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner_lines)

    try:
        data = json.loads(text)
        return {
            "category": str(data.get("category", "other")).lower(),
            "severity": str(data.get("severity", "medium")).lower(),
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
            "explanation": str(
                data.get("explanation", "AI could not determine the issue type.")
            )[:500],
            "summary": str(data.get("summary", "Community infrastructure issue"))[:100],
            "reasoning": str(data.get("reasoning", ""))[:1000],
            "alternative_categories": data.get("alternative_categories", {}),
            "is_emergency": bool(data.get("is_emergency", False)),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(
            "AI response parse failed",
            extra={"raw": raw[:200], "error": str(e)}
        )
        return {
            "category": "other",
            "severity": "medium",
            "confidence": 0.0,
            "explanation": "AI analysis was inconclusive. Category has been set to 'Other'.",
            "summary": "Community infrastructure issue",
            "reasoning": "",
            "alternative_categories": {},
            "is_emergency": False,
        }


async def _call_openai_vision(
    description: str,
    image_base64: Optional[str],
) -> Optional[dict]:
    """
    Calls OpenAI GPT-4o (which handles both text and vision natively).
    Returns parsed result dict or None on any failure (timeout, HTTP error, etc).

    GPT-4o is used for both image and text-only requests — it handles vision
    natively and is the most capable model for structured JSON output.
    """
    if not settings.openai_api_key:
        logger.info("OpenAI API key not set — skipping OpenAI call")
        return None

    payload = {
        "model": "gpt-4o",
        "max_tokens": 256,
        "temperature": 0.1,  # Low temperature for consistent classification
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(description, image_base64)},
        ],
    }

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=settings.ai_timeout_seconds,
            write=10.0,
            pool=5.0,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw_content = data["choices"][0]["message"]["content"]
        result = _parse_ai_response(raw_content)
        logger.info(
            "OpenAI categorization success",
            extra={
                "model": "gpt-4o",
                "category": result["category"],
                "confidence": result["confidence"],
            }
        )
        return result

    except httpx.TimeoutException:
        logger.warning("OpenAI API timeout", extra={"timeout_seconds": settings.ai_timeout_seconds})
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(
            "OpenAI API error",
            extra={
                "status": e.response.status_code,
                "body": e.response.text[:200],
            }
        )
        return None
    except Exception as e:
        logger.warning("OpenAI unexpected error", extra={"error": str(e)})
        return None


async def _call_gemini_vision(
    description: str,
    image_base64: Optional[str],
) -> Optional[dict]:
    """
    Calls Google Gemini 1.5 Flash Vision API as fallback to OpenAI.
    Returns parsed result dict or None on failure.

    Gemini 1.5 Flash is chosen for its:
    - Fast inference (good for real-time civic apps)
    - Vision capability with inline_data
    - Cost-effective pricing for high-volume civic use
    """
    api_key = settings.google_api_key or settings.gemini_api_key
    if not api_key:
        logger.info("Google API key not set — skipping Gemini call")
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash:generateContent?key={api_key}"
    )

    parts = []
    if image_base64:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_base64,
            }
        })
    parts.append({
        "text": (
            f"{SYSTEM_PROMPT}\n\n"
            f"Issue description: {description}\n\n"
            "Classify this civic infrastructure issue."
        )
    })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "maxOutputTokens": 512,   # Increase for chain-of-thought reasoning
            "temperature": 0.1,
            "responseMimeType": "application/json",  # Force JSON output
        },
    }

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=settings.ai_timeout_seconds,
            write=10.0,
            pool=5.0,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        raw_content = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        result = _parse_ai_response(raw_content)
        logger.info(
            "Gemini categorization success",
            extra={
                "model": "gemini-3.5-flash",
                "category": result["category"],
                "confidence": result["confidence"],
            }
        )
        return result

    except httpx.TimeoutException:
        logger.warning("Gemini API timeout", extra={"timeout_seconds": settings.ai_timeout_seconds})
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Gemini API HTTP error",
            extra={
                "status": e.response.status_code,
                "body": e.response.text[:200],
            }
        )
        return None
    except Exception as e:
        logger.warning("Gemini API error", extra={"error": str(e)})
        return None


async def _run_categorization(
    issue_id: str,
    image_path: Optional[str],
    description: str,
) -> dict:
    """
    Orchestrates the full AI categorization pipeline:

    1. Load image from disk as base64 (if image_path provided and file exists)
    2. Try OpenAI GPT-4o (primary)
    3. Fallback to Gemini 1.5 Flash Vision
    4. Fallback to zero-confidence default if both APIs fail
    5. Update issue fields in PostgreSQL
    6. Publish result to Redis (key: lumen:ai_result:{issue_id}, TTL: 5min)
       so the frontend can poll /ai/status/{id} if socket delivery fails

    Args:
        issue_id: UUID string of the issue to categorize
        image_path: Relative path within media_path (e.g. "uploads/abc.jpg"), or None
        description: Plain-text description of the civic issue

    Returns:
        dict with keys: category, severity, confidence, explanation, summary, is_emergency
    """
    # ── 1. Load image as base64 ───────────────────────────
    image_base64 = None
    if image_path:
        full_path = Path(settings.media_path) / image_path
        if full_path.exists():
            try:
                with open(full_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
                logger.info(
                    "Image loaded for AI analysis",
                    extra={
                        "path": str(full_path),
                        "size_bytes": full_path.stat().st_size,
                    }
                )
            except Exception as e:
                logger.warning(
                    "Could not load image for AI",
                    extra={
                        "path": str(full_path),
                        "error": str(e),
                    }
                )
        else:
            logger.info(
                "Image file not found — proceeding text-only",
                extra={"path": str(full_path)},
            )

    # PRIMARY: Google Gemini 3.5 Flash
    # Gemini is fast, vision-capable, and cost-effective for civic classification.
    # OpenAI GPT-4o is the fallback if Gemini is unavailable.
    # ── 2. Try Gemini FIRST (Google Technologies criterion) ──
    result = await _call_gemini_vision(description, image_base64)

    # ── 3. Fallback to OpenAI ────────────────────────────────
    if result is None:
        result = await _call_openai_vision(description, image_base64)

    # ── 4. Fallback to zero-confidence default ────────────
    if result is None:
        result = {
            "category": "other",
            "severity": "medium",
            "confidence": 0.0,
            "explanation": (
                "AI service was unavailable. "
                "Please select the correct category manually."
            ),
            "summary": "Community infrastructure issue",
            "is_emergency": False,
        }
        logger.warning(
            "All AI providers failed — using default result",
            extra={"issue_id": issue_id},
        )

    # ── 5. Update issue in database ──────────────────────
    # Uses the shared Celery engine (one pool per worker process, not per task).
    async with get_celery_session() as db:
        from app.models import Issue

        issue_result = await db.execute(
            select(Issue).where(Issue.id == uuid.UUID(issue_id))
        )
        issue = issue_result.scalar_one_or_none()

        if issue:
            issue.ai_category = result["category"]
            issue.ai_severity = result["severity"]
            issue.ai_confidence = result["confidence"]
            issue.ai_explanation = result["explanation"]
            issue.ai_summary = result["summary"]
            issue.ai_reasoning = result.get("reasoning", "")      # NEW
            issue.ai_alternatives = result.get("alternative_categories", {})  # NEW

            # Auto-promote to emergency if AI detects critical safety risk
            # and the issue hasn't already been flagged by the reporter
            if result["is_emergency"] and not issue.is_emergency:
                issue.is_emergency = True
                logger.warning(
                    "AI auto-promoted issue to emergency",
                    extra={
                        "issue_id": issue_id,
                        "explanation": result["explanation"],
                    }
                )

            await db.commit()
            logger.info(
                "Issue AI fields updated in database",
                extra={
                    "issue_id": issue_id,
                    "category": result["category"],
                    "severity": result["severity"],
                    "confidence": result["confidence"],
                }
            )
        else:
            logger.error(
                "Issue not found in database during AI update",
                extra={"issue_id": issue_id},
            )

    # ── 6. Publish result to Redis for polling ────────────
    # Direct Socket.IO emission from a Celery worker is architecturally
    # complex (workers don't share the FastAPI event loop or socketio instance).
    # The production pattern is: Celery publishes to Redis; FastAPI subscribes.
    # For this implementation: we store the result in Redis with a short TTL.
    # The frontend polls GET /ai/status/{id} as a WebSocket fallback.
    try:
        import redis as redis_sync

        r = redis_sync.from_url(settings.redis_url, decode_responses=True)
        r.setex(
            f"lumen:ai_result:{issue_id}",
            300,  # 5-minute TTL — frontend should poll within this window
            json.dumps({
                "issue_id": issue_id,
                "ai_category": result["category"],
                "ai_severity": result["severity"],
                "ai_confidence": result["confidence"],
                "ai_explanation": result["explanation"],
                "ai_summary": result["summary"],
                "ai_reasoning": result.get("reasoning", ""),            # NEW
                "ai_alternatives": result.get("alternative_categories", {}),  # NEW
            }),
        )
        r.close()
        logger.info("AI result published to Redis", extra={"issue_id": issue_id})
    except Exception as e:
        # Redis publish failure is non-fatal — DB was already updated
        logger.warning("Could not publish AI result to Redis", extra={"error": str(e)})

    return result


@celery_app.task(
    name="app.services.ai_categorizer.categorize_issue_task",
    bind=True,
    max_retries=2,
    default_retry_delay=10,  # seconds between retries
)
def categorize_issue_task(
    self,
    issue_id: str,
    image_path: Optional[str],
    description: str,
):
    """
    Celery task: Categorizes a civic issue using AI vision models.

    Called asynchronously after issue creation in POST /issues.
    Stores result in Redis for polling and updates DB directly.

    Retry strategy:
    - max_retries=2: Up to 2 automatic retries on transient failures
    - default_retry_delay=10: 10-second cooldown between retries
    - On MaxRetriesExceededError: returns a failure dict (does not raise)

    Args:
        issue_id: UUID string of the issue to categorize
        image_path: Relative media path or None
        description: Issue description text
    """
    try:
        # asyncio.run() starts a fresh event loop in the Celery worker process
        result = asyncio.run(_run_categorization(issue_id, image_path, description))
        logger.info(
            "AI categorization task completed successfully",
            extra={
                "issue_id": issue_id,
                "category": result.get("category"),
                "confidence": result.get("confidence"),
            }
        )
        return result
    except Exception as exc:
        logger.error(
            "AI categorization task failed",
            extra={
                "issue_id": issue_id,
                "error": str(exc),
                "retry_count": self.request.retries,
            }
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "AI categorization max retries exceeded — giving up",
                extra={"issue_id": issue_id},
            )
            return {"status": "failed", "issue_id": issue_id}
