"""
Lumen Autonomous Issue Triage Agent
A multi-step AI reasoning chain that perceives, reasons, and acts
on newly reported civic issues to assist officials.

Agent Architecture (ReAct pattern: Reason + Act):
  Step 1 — PERCEIVE: Load issue context (details, nearby issues, history)
  Step 2 — REASON: Call Gemini with function calling to analyze context
  Step 3 — ACT: Execute the recommended action (assign, escalate, flag)
  Step 4 — EXPLAIN: Store reasoning trace for admin transparency

Tools available to the agent:
  - get_issue_context: Loads full issue details and surrounding context
  - get_department_for_category: Maps category → responsible department
  - check_emergency_threshold: Determines if emergency escalation needed
  - check_duplicate_cluster: Checks if issue is part of a recurring cluster
  - get_queue_backlog: Gets current queue depth for load balancing

The agent reasons about all available context before recommending an action.
Its reasoning steps are stored and displayed to admins for transparency.
"""
import uuid
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.config import settings
from app.logging_config import logger

# ── Department mapping ────────────────────────────────────
DEPARTMENT_MAP = {
    "pothole":       "BBMP Roads",
    "water_leakage": "BWSSB (Water Supply)",
    "streetlight":   "BESCOM (Electricity)",
    "garbage":       "BBMP Solid Waste",
    "drainage":      "BBMP Storm Drains",
    "other":         "BBMP General",
}

# ── Triage priority matrix ────────────────────────────────
# Priority 1 = highest urgency, 10 = lowest
PRIORITY_MATRIX = {
    ("critical", True):  1,   # critical + emergency
    ("critical", False): 2,   # critical, not emergency
    ("high",     True):  2,   # high + emergency
    ("high",     False): 3,   # high, not emergency
    ("medium",   True):  4,   # medium + emergency
    ("medium",   False): 5,   # medium, not emergency
    ("low",      True):  6,   # low + emergency
    ("low",      False): 7,   # low, not emergency
}

# ── Agent tools (function definitions for Gemini function calling) ────
TRIAGE_TOOLS = [
    {
        "name": "get_department_recommendation",
        "description": (
            "Returns the recommended government department for a given "
            "issue category and the typical response time for that department."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "The issue category (pothole, water_leakage, etc.)"
                },
                "severity": {
                    "type": "string",
                    "description": "The issue severity (low, medium, high, critical)"
                }
            },
            "required": ["category", "severity"]
        }
    },
    {
        "name": "flag_for_emergency_escalation",
        "description": (
            "Flags the issue for immediate emergency escalation. "
            "Use when the issue poses immediate danger to life or property."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why this issue needs emergency escalation"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "request_additional_verification",
        "description": (
            "Flags the issue as needing more community verification before assignment. "
            "Use when confidence is low or the issue report is ambiguous."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why additional verification is needed"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "mark_as_likely_duplicate",
        "description": (
            "Marks the issue as likely a duplicate of a recurring problem in this area. "
            "Use when historical data shows this location has repeated issues."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern_description": {
                    "type": "string",
                    "description": "Description of the recurring pattern"
                }
            },
            "required": ["pattern_description"]
        }
    }
]


async def _call_gemini_with_tools(
    system_prompt: str,
    user_message: str,
) -> tuple[str, list[dict], list[dict]]:
    """
    Calls Gemini 3.5 Flash with function calling (tool use).
    Returns (final_text, tool_calls, reasoning_steps).

    The agent may call multiple tools in a reasoning loop before
    producing its final recommendation. This implements the
    ReAct (Reason + Act) pattern.
    """
    api_key = settings.google_api_key or settings.gemini_api_key
    if not api_key:
        return "", [], [{"step": "error", "content": "Google API key not configured"}]

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash:generateContent?key={api_key}"
    )

    tool_calls = []
    reasoning_steps = []
    messages = [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_message}"}]}]

    # Agentic loop — up to 5 reasoning iterations
    for iteration in range(5):
        payload = {
            "contents": messages,
            "tools": [{"function_declarations": TRIAGE_TOOLS}],
            "toolConfig": {"function_calling_config": {"mode": "AUTO"}},
            "generationConfig": {
                "temperature": 0.2,  # Slightly higher than classification for reasoning
                "maxOutputTokens": 1024,
            },
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
            ) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            candidate = data.get("candidates", [{}])[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            # Check if agent is calling a tool
            function_calls = [p for p in parts if "functionCall" in p]
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            text_response = " ".join(text_parts).strip()

            if text_response:
                reasoning_steps.append({
                    "iteration": iteration,
                    "type": "reasoning",
                    "content": text_response,
                })

            if not function_calls:
                # No more tool calls — agent has finished reasoning
                return text_response, tool_calls, reasoning_steps

            # Process tool calls
            tool_results = []
            for fc in function_calls:
                fn_name = fc["functionCall"]["name"]
                fn_args = fc["functionCall"].get("args", {})

                reasoning_steps.append({
                    "iteration": iteration,
                    "type": "tool_call",
                    "tool": fn_name,
                    "args": fn_args,
                })
                tool_calls.append({"tool": fn_name, "args": fn_args})

                # Execute tool and get result
                tool_result = _execute_tool(fn_name, fn_args)
                tool_results.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {"result": tool_result}
                    }
                })

                reasoning_steps.append({
                    "iteration": iteration,
                    "type": "tool_result",
                    "tool": fn_name,
                    "result": tool_result,
                })

            # Add model response and tool results to conversation
            messages.append({"role": "model", "parts": parts})
            messages.append({"role": "user", "parts": tool_results})

        except Exception as e:
            reasoning_steps.append({
                "iteration": iteration,
                "type": "error",
                "content": str(e),
            })
            logger.warning("Triage agent iteration failed", extra={"error": str(e), "iteration": iteration})
            break

    return "", tool_calls, reasoning_steps


def _execute_tool(tool_name: str, args: dict) -> dict:
    """
    Executes a triage agent tool call.
    Returns a structured result that Gemini can reason about.
    """
    if tool_name == "get_department_recommendation":
        category = args.get("category", "other")
        severity = args.get("severity", "medium")
        department = DEPARTMENT_MAP.get(category, "BBMP General")
        sla_hours = {
            "critical": 2,
            "high": 24,
            "medium": 72,
            "low": 168,
        }.get(severity, 72)
        return {
            "department": department,
            "sla_hours": sla_hours,
            "contact": f"{department} Control Room",
        }

    elif tool_name == "flag_for_emergency_escalation":
        return {
            "action": "escalate_emergency",
            "notified": "All on-duty officials",
            "sla_override": "2 hours",
        }

    elif tool_name == "request_additional_verification":
        return {
            "action": "request_verification",
            "target_verifications": 3,
            "reason": args.get("reason", "Low confidence report"),
        }

    elif tool_name == "mark_as_likely_duplicate":
        return {
            "action": "flag_duplicate",
            "pattern": args.get("pattern_description", "Recurring issue in area"),
        }

    return {"error": f"Unknown tool: {tool_name}"}


async def run_triage_agent(
    issue_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Main entry point for the Triage Agent.
    Loads issue context, runs the reasoning loop, saves the triage report.

    Returns the triage report dict.
    """
    from app.models import Issue, TriageReport
    from app.services.geo_utils import bounding_box

    # ── PERCEIVE: Load issue context ─────────────────────
    issue_result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = issue_result.scalar_one_or_none()
    if not issue:
        logger.warning("Triage agent: issue not found", extra={"issue_id": str(issue_id)})
        return {}

    # Load nearby issues (context for the agent)
    min_lat, max_lat, min_lng, max_lng = bounding_box(
        issue.latitude, issue.longitude, 500.0  # 500m context radius
    )
    nearby_result = await db.execute(
        select(Issue.title, Issue.status, Issue.ai_category)
        .where(
            and_(
                Issue.latitude.between(min_lat, max_lat),
                Issue.longitude.between(min_lng, max_lng),
                Issue.id != issue_id,
                Issue.status.notin_(["closed"]),
            )
        )
        .limit(5)
    )
    nearby_issues = [
        {"title": r[0], "status": r[1], "category": r[2]}
        for r in nearby_result.all()
    ]

    # Get queue backlog count for this category
    backlog_result = await db.execute(
        select(func.count(Issue.id)).where(
            Issue.ai_category == issue.ai_category,
            Issue.status.in_(["reported", "verified", "assigned"]),
        )
    )
    queue_backlog = backlog_result.scalar_one()

    # Compute base priority from severity matrix
    base_priority = PRIORITY_MATRIX.get(
        (issue.severity, issue.is_emergency),
        5
    )

    # ── BUILD AGENT PROMPT ────────────────────────────────
    system_prompt = """You are an autonomous Issue Triage Agent for Lumen, a civic infrastructure platform in Bengaluru.

Your job is to analyze a newly reported community issue and make an autonomous triage decision.

You have access to tools. Use them to determine:
1. Which government department should handle this issue
2. Whether emergency escalation is needed
3. Whether additional community verification is needed first
4. Whether this is part of a recurring problem pattern

After using the relevant tools, output a final JSON recommendation:
{
  "recommended_department": "<department name>",
  "recommended_priority": <1-10, 1=highest>,
  "recommended_action": "<auto_assign|escalate_emergency|request_verification|flag_duplicate|review>",
  "recommendation_summary": "<2-3 sentence plain language summary for officials>",
  "confidence": <0.0-1.0>
}

Be decisive. Officials rely on your recommendation to act faster."""

    user_message = f"""
New issue reported:
Title: {issue.title}
Description: {issue.description}
Category (AI detected): {issue.ai_category or 'not classified yet'}
Severity (AI detected): {issue.ai_severity or issue.severity}
Is Emergency: {issue.is_emergency}
Location: {issue.address or f'{issue.latitude:.4f}, {issue.longitude:.4f}'}
Ward: {issue.ward or 'unknown'}
Verifications so far: {issue.verification_count}

Nearby issues (within 500m):
{json.dumps(nearby_issues, indent=2) if nearby_issues else 'None'}

Current queue backlog for this category: {queue_backlog} open issues

AI confidence in classification: {issue.ai_confidence or 0:.0%}

Please analyze this issue and use the available tools to make a triage recommendation.
"""

    # ── REASON + ACT: Run the agent ───────────────────────
    final_text, tool_calls, reasoning_steps = await _call_gemini_with_tools(
        system_prompt, user_message
    )

    # ── Parse final recommendation from agent output ──────
    recommendation = {
        "recommended_department": DEPARTMENT_MAP.get(issue.ai_category or "other", "BBMP General"),
        "recommended_priority": base_priority,
        "recommended_action": "escalate_emergency" if issue.is_emergency else "review",
        "recommendation_summary": f"Issue reported in {issue.ward or 'unknown ward'}. "
                                   f"Recommended for {DEPARTMENT_MAP.get(issue.ai_category or 'other', 'BBMP')}.",
        "confidence": 0.5,
    }

    # Try to parse the JSON from the agent's final text
    if final_text:
        parsed = {}
        try:
            # 1. Try raw JSON load
            parsed = json.loads(final_text.strip())
        except (json.JSONDecodeError, ValueError):
            # 2. Try markdown code block extraction
            import re
            code_block = re.search(r'```json\s*(.*?)\s*```', final_text, re.DOTALL)
            if code_block:
                try:
                    parsed = json.loads(code_block.group(1).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            
            # 3. Brace scanner fallback if still empty
            if not parsed:
                start = final_text.find('{')
                if start != -1:
                    count = 0
                    for i in range(start, len(final_text)):
                        if final_text[i] == '{':
                            count += 1
                        elif final_text[i] == '}':
                            count -= 1
                        if count == 0:
                            try:
                                parsed = json.loads(final_text[start:i+1])
                                break
                            except (json.JSONDecodeError, ValueError):
                                break
        if parsed:
            recommendation.update({
                k: v for k, v in parsed.items()
                if k in recommendation
            })

    # Override from tool calls if agent explicitly called a tool
    for tc in tool_calls:
        if tc["tool"] == "flag_for_emergency_escalation":
            recommendation["recommended_action"] = "escalate_emergency"
            recommendation["recommended_priority"] = 1
        elif tc["tool"] == "request_additional_verification":
            recommendation["recommended_action"] = "request_verification"
        elif tc["tool"] == "mark_as_likely_duplicate":
            recommendation["recommended_action"] = "flag_duplicate"
        elif tc["tool"] == "get_department_recommendation":
            if "department" in tc.get("result", {}):
                recommendation["recommended_department"] = tc["result"]["department"]

    # ── Save triage report ────────────────────────────────
    triage = TriageReport(
        issue_id=issue_id,
        reasoning_steps=reasoning_steps,
        recommended_department=recommendation["recommended_department"],
        recommended_priority=min(10, max(1, int(recommendation["recommended_priority"]))),
        recommended_action=recommendation["recommended_action"],
        recommendation_summary=recommendation["recommendation_summary"],
        confidence=min(1.0, max(0.0, float(recommendation["confidence"]))),
        agent_model="gemini-3.5-flash",
        auto_applied=False,
    )
    db.add(triage)
    await db.flush()

    logger.info(
        "Triage agent completed",
        extra={
            "issue_id": str(issue_id),
            "action": recommendation["recommended_action"],
            "priority": recommendation["recommended_priority"],
            "department": recommendation["recommended_department"],
            "iterations": len([s for s in reasoning_steps if s.get("type") == "tool_call"]),
        }
    )

    return {
        "triage_id": str(triage.id),
        "issue_id": str(issue_id),
        **recommendation,
        "reasoning_steps": reasoning_steps,
    }


from app.celery_app import celery_app


@celery_app.task(
    name="app.services.triage_agent.run_triage_task",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def run_triage_task(self, issue_id: str):
    """
    Celery task: runs the Triage Agent for a newly submitted issue.
    Called asynchronously after issue creation (alongside AI categorization).
    Results stored in triage_reports table and visible in admin queue.
    """
    import asyncio

    async def _run():
        from app.celery_db import get_celery_session
        async with get_celery_session() as db:
            result = await run_triage_agent(
                issue_id=uuid.UUID(issue_id),
                db=db,
            )
            await db.commit()
            return result

    try:
        result = asyncio.run(_run())
        logger.info("Triage task completed", extra={"issue_id": issue_id})
        return result
    except Exception as exc:
        logger.error("Triage task failed", extra={"issue_id": issue_id, "error": str(exc)})
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass
        return {}
