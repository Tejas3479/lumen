import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models import Issue, Category, WardReport, User
from app.services.ward_report_agent import (
    _generate_fallback_narrative,
    _generate_ward_narrative,
    _generate_all_ward_reports,
)

# Helpers
async def _register_user(client, email: str, username: str, display_name: str = "User") -> dict:
    reg = await client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "username": username,
        "display_name": display_name,
    })
    assert reg.status_code == 201
    return {"headers": {"Authorization": f"Bearer {reg.json()['access_token']}"}, "data": reg.json()}


def test_fallback_narrative():
    stats = {
        "new_issues": 10,
        "resolved_issues": 4,
        "open_issues": 6,
        "top_category": "garbage",
    }
    report = _generate_fallback_narrative("HSR Layout", stats)
    assert report["headline"] == "HSR Layout saw 10 new issue reports this week, with 4 resolved."
    assert "reported 10 infrastructure issues" in report["narrative"]
    assert "4 were resolved" in report["narrative"]
    assert "garbage" in report["narrative"]
    assert report["key_achievements"] == ["4 issues resolved this week"]
    assert report["key_concerns"] == ["6 issues still open"]


@pytest.mark.asyncio
async def test_generate_ward_narrative_fallback_no_key():
    # If no key, it should fallback
    with patch("app.services.ward_report_agent.settings") as mock_settings:
        mock_settings.google_api_key = None
        mock_settings.gemini_api_key = None
        stats = {
            "new_issues": 5,
            "resolved_issues": 2,
            "open_issues": 3,
            "top_category": "drainage",
        }
        report = await _generate_ward_narrative("HSR Layout", stats)
        assert "5 new issue reports" in report["headline"]


@pytest.mark.asyncio
async def test_generate_ward_narrative_gemini_success():
    with patch("app.services.ward_report_agent.settings") as mock_settings:
        mock_settings.google_api_key = "test_key"
        stats = {
            "new_issues": 5,
            "resolved_issues": 2,
            "open_issues": 3,
            "top_category": "drainage",
        }

        # Mock httpx response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"headline": "HSR Layout improves", "narrative": "Progress made.", "key_achievements": ["Cleaned drainage"], "key_concerns": ["Potholes"]}'
                            }
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            report = await _generate_ward_narrative("HSR Layout", stats)
            assert report["headline"] == "HSR Layout improves"
            assert report["narrative"] == "Progress made."
            assert report["key_achievements"] == ["Cleaned drainage"]
            assert report["key_concerns"] == ["Potholes"]


@pytest.mark.asyncio
async def test_generate_all_ward_reports_logic(db_session):
    # Setup test categories and issues
    cat1 = Category(id=uuid.uuid4(), name="garbage", display_name="Garbage")
    db_session.add(cat1)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        email="citizen@lumen.org",
        username="citizen1",
        display_name="Citizen",
    )
    db_session.add(user)
    await db_session.flush()

    # Create issues in HSR Layout ward
    now = datetime.now(timezone.utc)
    issue1 = Issue(
        id=uuid.uuid4(),
        title="Overflowing trash bin",
        description="Near park",
        latitude=12.91,
        longitude=77.64,
        category_id=cat1.id,
        reporter_id=user.id,
        ward="HSR Layout",
        created_at=now - timedelta(days=2),
        status="open",
    )
    db_session.add(issue1)
    await db_session.flush()

    # Mock Gemini so we don't hit the API
    with patch("app.services.ward_report_agent.settings") as mock_settings:
        mock_settings.google_api_key = None
        mock_settings.gemini_api_key = None

        # Patch get_celery_session to return our db_session
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__.return_value = db_session

        with patch("app.celery_db.get_celery_session", return_value=mock_session_ctx):
            result = await _generate_all_ward_reports()
            assert result["generated"] == 1
            assert "HSR Layout" in result["wards"]

            # Query db to verify report was saved
            q = await db_session.execute(select(WardReport).where(WardReport.ward == "HSR Layout"))
            report = q.scalar_one_or_none()
            assert report is not None
            assert report.stats["new_issues"] == 1
            assert report.stats["open_issues"] == 1
            assert "HSR Layout saw 1 new" in report.headline


@pytest.mark.asyncio
async def test_get_ward_report_endpoint(client, db_session):
    # Create a ward report directly
    now = datetime.now(timezone.utc)
    report = WardReport(
        id=uuid.uuid4(),
        ward="Koramangala",
        week_start=now - timedelta(days=7),
        week_end=now,
        stats={"new_issues": 3, "resolved_issues": 1, "open_issues": 2},
        headline="Koramangala updates",
        narrative="This week in Koramangala...",
        key_achievements=["Fixed streetlights"],
        key_concerns=["Pothole on 80ft road"],
        agent_model="gemini-3.5-flash",
        generated_at=now,
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.commit()

    # Get non-existent report -> 404
    resp = await client.get("/analytics/ward-report/NonexistentWard")
    assert resp.status_code == 404

    # Get existent report
    resp = await client.get("/analytics/ward-report/Koramangala")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ward"] == "Koramangala"
    assert data["headline"] == "Koramangala updates"
    assert data["key_achievements"] == ["Fixed streetlights"]
