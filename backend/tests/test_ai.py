"""
Tests: AI Categorization Routes and Feedback
Covers:
  - Unit tests for _parse_ai_response: valid JSON, markdown-fenced JSON,
    malformed input, missing fields, out-of-range confidence clamping
  - Integration tests for AI routes via HTTP client:
    status endpoint (pending / with DB data), feedback logging,
    non-existent issue 404, re-categorize dispatch
"""
import pytest
import json
import uuid
from app.services.ai_categorizer import _parse_ai_response


# =============================================================
# Unit Tests — _parse_ai_response
# =============================================================

def test_parse_valid_json():
    """Correctly parses a well-formed AI response JSON."""
    raw = json.dumps({
        "category": "pothole",
        "severity": "high",
        "confidence": 0.91,
        "explanation": "Road surface depression visible.",
        "summary": "Large pothole",
        "reasoning": "Large depression on high-traffic road.",
        "alternative_categories": {"other": 0.05},
        "is_emergency": False,
    })
    result = _parse_ai_response(raw)
    assert result["category"] == "pothole"
    assert result["severity"] == "high"
    assert result["confidence"] == pytest.approx(0.91)
    assert result["explanation"] == "Road surface depression visible."
    assert result["summary"] == "Large pothole"
    assert result["reasoning"] == "Large depression on high-traffic road."
    assert result["alternative_categories"] == {"other": 0.05}
    assert result["is_emergency"] is False


def test_parse_markdown_fenced_json():
    """Strips ```json … ``` fences before parsing."""
    raw = """```json
{"category":"water_leakage","severity":"critical","confidence":0.96,
"explanation":"Active pipe burst on residential road.","summary":"Pipe burst","is_emergency":true}
```"""
    result = _parse_ai_response(raw)
    assert result["category"] == "water_leakage"
    assert result["severity"] == "critical"
    assert result["confidence"] == pytest.approx(0.96)
    assert result["is_emergency"] is True


def test_parse_markdown_fenced_no_lang_tag():
    """Strips plain ``` fences (no language tag) before parsing."""
    raw = """```
{"category":"drainage","severity":"medium","confidence":0.75,
"explanation":"Blocked drain.","summary":"Drain blocked","is_emergency":false}
```"""
    result = _parse_ai_response(raw)
    assert result["category"] == "drainage"
    assert result["confidence"] == pytest.approx(0.75)


def test_parse_malformed_json_returns_default():
    """Returns safe defaults when response is not valid JSON."""
    result = _parse_ai_response("This is not JSON at all!")
    assert result["category"] == "other"
    assert result["confidence"] == 0.0
    assert "inconclusive" in result["explanation"].lower()
    assert result["is_emergency"] is False


def test_parse_missing_fields_uses_defaults():
    """Missing optional fields fall back to safe defaults."""
    raw = json.dumps({"category": "garbage"})
    result = _parse_ai_response(raw)
    assert result["category"] == "garbage"
    assert result["severity"] == "medium"      # default
    assert result["confidence"] == 0.5         # default
    assert result["is_emergency"] is False      # default
    assert result["reasoning"] == ""           # default
    assert result["alternative_categories"] == {} # default
    assert len(result["explanation"]) > 0


def test_parse_confidence_clamped_high():
    """Confidence values > 1.0 are clamped to 1.0."""
    raw = json.dumps({
        "category": "pothole",
        "severity": "low",
        "confidence": 1.5,   # Over 1.0 — must be clamped
        "explanation": "test",
        "summary": "test",
        "is_emergency": False,
    })
    result = _parse_ai_response(raw)
    assert result["confidence"] == pytest.approx(1.0)


def test_parse_confidence_clamped_low():
    """Confidence values < 0.0 are clamped to 0.0."""
    raw = json.dumps({
        "category": "streetlight",
        "severity": "medium",
        "confidence": -0.5,  # Below 0.0 — must be clamped
        "explanation": "test",
        "summary": "test",
        "is_emergency": False,
    })
    result = _parse_ai_response(raw)
    assert result["confidence"] == pytest.approx(0.0)


def test_parse_explanation_truncated():
    """Explanation strings longer than 500 chars are truncated."""
    long_text = "A" * 600
    raw = json.dumps({
        "category": "other",
        "severity": "low",
        "confidence": 0.5,
        "explanation": long_text,
        "summary": "test",
        "is_emergency": False,
    })
    result = _parse_ai_response(raw)
    assert len(result["explanation"]) <= 500


# =============================================================
# Integration Tests — AI Routes
# =============================================================

async def _register_and_create_issue(client):
    """
    Helper: registers a unique test user, creates an issue, returns (token, issue_id).
    Uses a random suffix to avoid unique-constraint conflicts across tests.
    """
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/auth/register", json={
        "email": f"ai_test_{suffix}@lumen.com",
        "password": "password123",
        "username": f"ai_tester_{suffix}",
        "display_name": "AI Test User",
    })
    assert reg.status_code in (200, 201), f"Registration failed: {reg.text}"
    token = reg.json()["access_token"]

    issue_resp = await client.post(
        "/issues",
        data={
            "title": "Large pothole near main junction",
            "description": "Large pothole near the main junction causing vehicle damage and road closures.",
            "latitude": "12.9716",
            "longitude": "77.5946",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code in (200, 201), f"Issue creation failed: {issue_resp.text}"
    return token, issue_resp.json()["id"]


@pytest.mark.asyncio
async def test_ai_status_pending_or_complete(client):
    """
    AI status for a newly created issue returns either pending (task still running)
    or a result dict (if the Celery task ran synchronously in test environment).
    Both are valid outcomes for this test.
    """
    _token, issue_id = await _register_and_create_issue(client)
    response = await client.get(f"/ai/status/{issue_id}")
    assert response.status_code == 200
    data = response.json()
    # Must contain either issue_id with AI data OR a status=pending message
    assert "issue_id" in data or "status" in data


@pytest.mark.asyncio
async def test_ai_status_nonexistent_issue_returns_404(client):
    """GET /ai/status/{id} with a non-existent UUID returns 404."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/ai/status/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ai_feedback_correction_logged(client):
    """
    POST /ai/feedback with a user correction returns status=correction_logged
    and can be submitted without auth (anonymous correction allowed).
    """
    _token, issue_id = await _register_and_create_issue(client)
    response = await client.post(
        "/ai/feedback",
        json={
            "issue_id": issue_id,
            "corrected_category": "water_leakage",
            "corrected_severity": "high",
            "user_comment": "This is actually a water leakage, not a pothole.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "correction_logged"
    assert data["issue_id"] == issue_id


@pytest.mark.asyncio
async def test_ai_feedback_with_auth(client):
    """POST /ai/feedback with a Bearer token also succeeds and logs the actor."""
    token, issue_id = await _register_and_create_issue(client)
    response = await client.post(
        "/ai/feedback",
        json={
            "issue_id": issue_id,
            "corrected_category": "drainage",
            "corrected_severity": "medium",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "correction_logged"


@pytest.mark.asyncio
async def test_ai_feedback_nonexistent_issue_returns_404(client):
    """POST /ai/feedback with a non-existent issue UUID returns 404."""
    fake_id = str(uuid.uuid4())
    response = await client.post(
        "/ai/feedback",
        json={
            "issue_id": fake_id,
            "corrected_category": "pothole",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_recategorize_dispatches_task(client):
    """
    GET /ai/categorize/{id} on an existing issue returns status=queued.
    (Celery task is dispatched; we don't wait for completion in tests.)
    """
    _token, issue_id = await _register_and_create_issue(client)
    response = await client.get(f"/ai/categorize/{issue_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["issue_id"] == issue_id


@pytest.mark.asyncio
async def test_recategorize_nonexistent_issue_returns_404(client):
    """GET /ai/categorize/{id} with a non-existent UUID returns 404."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/ai/categorize/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_agents_status(client, db_session):
    """GET /ai/agents/status returns the status and metrics of Lumen's agents."""
    # Seed a triage report to ensure metrics can increment
    from app.models import TriageReport, Category, User, Issue, WardReport
    from datetime import datetime, timezone
    import uuid as uuid_pkg

    # Create category, user, issue for triage report
    cat = Category(id=uuid_pkg.uuid4(), name="garbage", display_name="Garbage")
    db_session.add(cat)
    await db_session.flush()

    user = User(id=uuid_pkg.uuid4(), email="agent_test@lumen.org", username="agent_test", display_name="Agent Tester")
    db_session.add(user)
    await db_session.flush()

    issue = Issue(
        id=uuid_pkg.uuid4(),
        title="Overflowing trash",
        description="Trash all over the sidewalk",
        latitude=12.91,
        longitude=77.64,
        category_id=cat.id,
        reporter_id=user.id,
        ward="HSR Layout",
        created_at=datetime.now(timezone.utc),
        status="open"
    )
    db_session.add(issue)
    await db_session.flush()

    triage = TriageReport(
        id=uuid_pkg.uuid4(),
        issue_id=issue.id,
        recommended_priority=1,
        recommended_department="BBMP Health Dept",
        recommended_action="assign_official",
        recommendation_summary="Highly visible garbage concern.",
        reasoning_steps=[]
    )
    db_session.add(triage)

    # Seed an escalated issue
    issue_escalated = Issue(
        id=uuid_pkg.uuid4(),
        title="Stalled Pothole",
        description="Deep pothole left unrepaired",
        latitude=12.92,
        longitude=77.65,
        category_id=cat.id,
        reporter_id=user.id,
        ward="Koramangala",
        created_at=datetime.now(timezone.utc),
        status="assigned",
        escalation_count=1,
        escalated_at=datetime.now(timezone.utc)
    )
    db_session.add(issue_escalated)

    # Seed a ward report
    report = WardReport(
        id=uuid_pkg.uuid4(),
        ward="Koramangala",
        week_start=datetime.now(timezone.utc),
        week_end=datetime.now(timezone.utc),
        stats={},
        headline="Koramangala Weekly",
        narrative="Progress.",
        key_achievements=["Fixed light"],
        key_concerns=["Garbage"],
        agent_model="gemini-3.5-flash"
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.commit()

    response = await client.get("/ai/agents/status")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) == 3

    triage_agent = next(a for a in data["agents"] if a["id"] == "triage_agent")
    assert triage_agent["name"] == "Issue Triage Agent"
    assert triage_agent["metrics"]["total_triaged_issues"] >= 1

    escalation_agent = next(a for a in data["agents"] if a["id"] == "escalation_agent")
    assert escalation_agent["name"] == "Proactive Escalation Agent"
    assert escalation_agent["metrics"]["active_escalations"] >= 1

    ward_report_agent = next(a for a in data["agents"] if a["id"] == "ward_report_agent")
    assert ward_report_agent["name"] == "Weekly Ward Report Agent"
    assert ward_report_agent["metrics"]["total_reports_generated"] >= 1

