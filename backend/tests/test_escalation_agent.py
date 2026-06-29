import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select, update as sa_update
from app.models import Issue, Category, StatusHistory, IssueAuditLog, User
from app.services.escalation_agent import _get_sla_hours, _find_stalled_issues, _run_escalation_check

# ─── Helpers ──────────────────────────────────────────────────

async def _register_user(client, email: str, username: str, display_name: str = "User") -> dict:
    """Register a user and return auth headers + user data."""
    reg = await client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "username": username,
        "display_name": display_name,
    })
    assert reg.status_code == 201, f"Register failed for {email}: {reg.text}"
    return {"headers": {"Authorization": f"Bearer {reg.json()['access_token']}"}, "data": reg.json()}


async def _make_admin(db_session, email: str):
    """Elevate a user to admin in the test database."""
    await db_session.execute(
        sa_update(User).where(User.email == email).values(is_admin=True, is_official=True)
    )
    await db_session.flush()

# ─── Tests ────────────────────────────────────────────────────

def test_get_sla_hours():
    # pothole / high / unverified
    # pothole base: 120
    # high severity factor: 0.5
    # unverified stage factor: 0.4
    # Expected: 120 * 0.5 * 0.4 = 24.0
    assert _get_sla_hours("pothole", "high", "unverified") == 24.0

    # garbage / critical / assigned
    # garbage base: 48
    # critical severity factor: 0.25
    # assigned stage factor: 0.2
    # Expected: 48 * 0.25 * 0.2 = 2.4
    assert _get_sla_hours("garbage", "critical", "assigned") == pytest.approx(2.4)

    # streetlight / medium / in_progress
    # streetlight base: 96
    # medium severity factor: 1.0
    # in_progress stage factor: 2.0
    # Expected: 96 * 1.0 * 2.0 = 192.0
    assert _get_sla_hours("streetlight", "medium", "in_progress") == 192.0


@pytest.mark.asyncio
async def test_find_stalled_issues_db(db_session):
    # Create category
    category = Category(id=uuid.uuid4(), name="garbage", display_name="Garbage", avg_resolution_days=2.0)
    db_session.add(category)
    await db_session.flush()

    # Issue 1: Reported 3 days ago, category = garbage, severity = high
    # SLA for high/unverified = 48 * 0.5 * 0.4 = 9.6 hours.
    # Stalled!
    issue_stalled = Issue(
        id=uuid.uuid4(),
        title="Stalled Issue",
        description="Test desc",
        category_id=category.id,
        severity="high",
        status="reported",
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
        updated_at=datetime.now(timezone.utc) - timedelta(days=3),
    )

    # Issue 2: Reported 2 hours ago. Not stalled.
    issue_not_stalled = Issue(
        id=uuid.uuid4(),
        title="Not Stalled Issue",
        description="Test desc",
        category_id=category.id,
        severity="high",
        status="reported",
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    # Issue 3: Stalled, but escalation_count = 3 (reached cap, shouldn't be picked up)
    issue_max_escalation = Issue(
        id=uuid.uuid4(),
        title="Max Escalation Issue",
        description="Test desc",
        category_id=category.id,
        severity="high",
        status="reported",
        latitude=12.9716,
        longitude=77.5946,
        escalation_count=3,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
        updated_at=datetime.now(timezone.utc) - timedelta(days=3),
    )

    db_session.add_all([issue_stalled, issue_not_stalled, issue_max_escalation])
    await db_session.flush()

    stalled = await _find_stalled_issues(db_session)
    assert len(stalled) == 1
    assert stalled[0][0].id == issue_stalled.id
    assert stalled[0][1] == "unverified"
    assert stalled[0][2] > 0


@pytest.mark.asyncio
async def test_run_escalation_check_logic(db_session):
    # Add a user to serve as reporter (so notify_issue_status_change doesn't fail or return early)
    user = User(
        id=uuid.uuid4(),
        email="reporter@test.com",
        username="reporter",
        display_name="Reporter",
        password_hash="...",
    )
    db_session.add(user)
    await db_session.flush()

    # Create category
    category = Category(id=uuid.uuid4(), name="pothole", display_name="Pothole", avg_resolution_days=5.0)
    db_session.add(category)
    await db_session.flush()

    # Stalled reported issue
    issue = Issue(
        id=uuid.uuid4(),
        title="Pothole Issue",
        description="Test desc",
        category_id=category.id,
        severity="medium",
        status="reported",
        reporter_id=user.id,
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        updated_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(issue)
    await db_session.flush()

    # Patch get_celery_session to return our db_session
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = db_session

    with patch("app.celery_db.get_celery_session", return_value=mock_session_context), \
         patch("app.services.notification.notify_issue_status_change", new_callable=AsyncMock) as mock_notify:
        
        result = await _run_escalation_check()
        assert result["escalated"] == 1

        # Check that issue columns were updated
        await db_session.refresh(issue)
        assert issue.escalation_count == 1
        assert issue.escalated_at is not None

        # Check status history was created
        sh_result = await db_session.execute(select(StatusHistory).where(StatusHistory.issue_id == issue.id))
        sh = sh_result.scalars().all()
        assert len(sh) == 1
        assert "⚠️ ESCALATION #1" in sh[0].note

        # Check audit log was created
        al_result = await db_session.execute(select(IssueAuditLog).where(IssueAuditLog.issue_id == issue.id))
        al = al_result.scalars().all()
        assert len(al) == 1
        assert al[0].action == "auto_escalated"
        assert al[0].after_state["escalation_count"] == 1

        # Check notification was sent
        mock_notify.assert_called_once_with(
            reporter_id=str(user.id),
            issue_id=str(issue.id),
            issue_title=issue.title,
            new_status="escalated",
            db=db_session,
        )


@pytest.mark.asyncio
async def test_escalations_endpoint(client, db_session):
    # Register admin user
    admin = await _register_user(client, "admin_esc@lumen.com", "admin_esc", "Admin Esc")
    await _make_admin(db_session, "admin_esc@lumen.com")

    # Create two escalated issues
    issue1 = Issue(
        id=uuid.uuid4(),
        title="Escalated Issue 1",
        description="Desc 1",
        severity="medium",
        status="reported",
        escalation_count=1,
        escalated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        latitude=12.9716,
        longitude=77.5946,
    )
    issue2 = Issue(
        id=uuid.uuid4(),
        title="Escalated Issue 2",
        description="Desc 2",
        severity="medium",
        status="assigned",
        escalation_count=2,
        escalated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        latitude=12.9716,
        longitude=77.5946,
    )
    issue_resolved = Issue(
        id=uuid.uuid4(),
        title="Escalated but Resolved",
        description="Desc 3",
        severity="medium",
        status="resolved",
        escalation_count=2,
        escalated_at=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
    )

    db_session.add_all([issue1, issue2, issue_resolved])
    await db_session.flush()

    resp = await client.get("/admin/escalations", headers=admin["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    # issue2 should be first because it has escalation_count=2 (higher urgency)
    assert data["escalated_issues"][0]["id"] == str(issue2.id)
    assert data["escalated_issues"][0]["escalation_count"] == 2
    assert data["escalated_issues"][1]["id"] == str(issue1.id)
    assert data["escalated_issues"][1]["escalation_count"] == 1
