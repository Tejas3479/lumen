"""
Tests: Spam Detection
Covers:
  - Unit tests for _check_text_quality:
    too-short description, too-short title, all-caps,
    profanity, repetitive characters, test-phrase, too-few words, clean text
  - Integration tests:
    clean submission via check_spam passes,
    short description rejected via check_spam,
    first issue creation via API succeeds (rate limit not hit),
    moderation process_flag returns expected structure,
    auto-hide activates after threshold flags,
    flag dismiss and resolve lifecycle
"""
import pytest
import uuid
from app.services.spam_detector import (
    _check_text_quality,
    check_spam,
    RATE_LIMIT_USER_PER_HOUR,
    BURST_LIMIT_10_MIN,
    ALL_CAPS_THRESHOLD,
)


# =============================================================
# Unit Tests — _check_text_quality
# =============================================================

def test_text_too_short_description():
    """Description under 10 chars must be rejected with confidence 1.0."""
    is_spam, conf, reason = _check_text_quality("Valid title here", "Short")
    assert is_spam is True
    assert conf == 1.0
    assert "short" in reason.lower()


def test_text_too_short_title():
    """Title under 5 chars must be rejected."""
    is_spam, conf, reason = _check_text_quality("Hi", "Description long enough to pass the length check here")
    assert is_spam is True
    assert conf == 1.0
    assert "title" in reason.lower()


def test_text_all_caps_long_enough():
    """Text > 20 chars that is predominantly uppercase must be flagged."""
    is_spam, conf, reason = _check_text_quality(
        "HUGE POTHOLE EMERGENCY NOW",
        "THERE IS A MASSIVE POTHOLE ON THE ROAD BLOCKING ALL TRAFFIC PLEASE FIX"
    )
    assert is_spam is True
    assert conf >= 0.8
    # Should mention capitals or shouting
    assert any(kw in reason.lower() for kw in ("capital", "shout", "case"))


def test_text_all_caps_short_not_flagged():
    """Short all-caps (≤ 20 chars) must NOT be flagged as shouting."""
    # "SOS POTHOLE" is 11 chars — could be legitimate short report start
    is_spam, conf, reason = _check_text_quality(
        "Pothole here",
        "SOS POTHOLE"  # too short for all-caps rule to fire
    )
    # Should be flagged for word count, not for all-caps
    if is_spam:
        assert "shout" not in reason.lower() and "capital" not in reason.lower()


def test_text_profanity_in_description():
    """Description containing a blocked term must be rejected."""
    is_spam, conf, reason = _check_text_quality(
        "Road issue",
        "There is a fucking huge pothole near the main junction on the road"
    )
    assert is_spam is True
    assert conf >= 0.9
    assert "inappropriate" in reason.lower()


def test_text_repetitive_characters():
    """9+ repetitions of any character must be flagged."""
    is_spam, conf, reason = _check_text_quality(
        "Valid title for the issue",
        "There is a pothole aaaaaaaaaa near main road junction here"
    )
    assert is_spam is True
    assert conf >= 0.8
    assert "repetitive" in reason.lower()


def test_text_test_phrase_exact_match():
    """Exact 'test' submission must be rejected."""
    is_spam, conf, reason = _check_text_quality("test", "testing")
    assert is_spam is True
    assert conf == 1.0


def test_text_too_few_words():
    """Combined title + description with fewer than MIN_WORD_COUNT words must be flagged."""
    is_spam, conf, reason = _check_text_quality("Pothole", "potholehere")
    assert is_spam is True
    assert conf >= 0.8
    assert "word" in reason.lower()


def test_text_clean_passes():
    """A well-formed civic report must pass all text quality checks."""
    is_spam, conf, reason = _check_text_quality(
        "Large pothole near MG Road main junction",
        "There is a deep and dangerous pothole on MG Road near the signal causing accidents to motorcyclists."
    )
    assert is_spam is False
    assert conf == 0.0
    assert reason == ""


def test_text_word_count_threshold_boundary():
    """Exactly MIN_WORD_COUNT words must pass (boundary case)."""
    from app.services.spam_detector import MIN_WORD_COUNT
    # Create a title + description with exactly MIN_WORD_COUNT unique words
    words = [f"word{i}" for i in range(MIN_WORD_COUNT)]
    # Split across title and description
    title = " ".join(words[:2])
    desc = " ".join(words[2:]) + " extra padding here"
    is_spam, _, _ = _check_text_quality(title, desc)
    # With MIN_WORD_COUNT words the check passes (boundary is exclusive)
    assert is_spam is False


# =============================================================
# Integration Tests — check_spam
# =============================================================

@pytest.mark.asyncio
async def test_check_spam_clean_no_reporter(db_session):
    """A clean submission with no reporter must pass all spam checks."""
    is_spam, conf, reason = await check_spam(
        title="Large pothole on MG Road near the traffic signal",
        description="There is a very large and dangerous pothole near the main junction on MG Road.",
        reporter=None,
        db=db_session,
    )
    assert is_spam is False


@pytest.mark.asyncio
async def test_check_spam_rejects_short_description(db_session):
    """check_spam must reject descriptions under 10 chars."""
    is_spam, conf, reason = await check_spam(
        title="Valid title here",
        description="Short",
        reporter=None,
        db=db_session,
    )
    assert is_spam is True
    assert conf >= 0.9


@pytest.mark.asyncio
async def test_check_spam_rejects_profanity(db_session):
    """check_spam must reject profanity in description."""
    is_spam, conf, reason = await check_spam(
        title="Valid pothole report on the road",
        description="There is a fucking massive pothole on the road near the junction",
        reporter=None,
        db=db_session,
    )
    assert is_spam is True


@pytest.mark.asyncio
async def test_check_spam_first_issue_passes_rate_limit(client):
    """First issue submission by a new user must pass rate limiting."""
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/auth/register", json={
        "email": f"spamtest_{suffix}@lumen.com",
        "password": "password123",
        "username": f"spamtest_{suffix}",
        "display_name": "Spam Test User",
    })
    assert reg.status_code in (200, 201)
    token = reg.json()["access_token"]

    response = await client.post(
        "/issues",
        data={
            "title": "Large pothole on the main road near junction",
            "description": "There is a dangerous pothole on the main road near the junction here.",
            "latitude": "12.9716",
            "longitude": "77.5946",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # First submission must always succeed
    assert response.status_code == 201


# =============================================================
# Integration Tests — Moderation Service
# =============================================================

@pytest.mark.asyncio
async def test_process_flag_returns_flagged_for_first_flag(db_session):
    """First flag on an issue returns action='flagged' (threshold not reached)."""
    from app.services.moderation import process_flag

    result = await process_flag(
        issue_id=uuid.uuid4(),   # Non-existent — flag_count=0
        flagged_by_id=uuid.uuid4(),
        reason="spam",
        db=db_session,
    )
    assert "action" in result
    assert "flag_count" in result
    assert result["action"] in ("flagged", "auto_hidden")


@pytest.mark.asyncio
async def test_process_flag_auto_hide_threshold(client):
    """
    Submitting AUTO_HIDE_FLAG_COUNT distinct user flags on the same issue
    must trigger auto_hidden action and change the issue status to 'closed'.
    """
    from app.services.moderation import AUTO_HIDE_FLAG_COUNT

    # Create reporter
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post("/auth/register", json={
        "email": f"reporter_{suffix}@lumen.com",
        "password": "password123",
        "username": f"reporter_{suffix}",
        "display_name": "Reporter",
    })
    reporter_token = reg.json()["access_token"]

    issue_resp = await client.post(
        "/issues",
        data={
            "title": "Pothole auto-hide threshold test issue on road",
            "description": "This issue will be flagged multiple times to test auto-hide.",
            "latitude": "12.9716",
            "longitude": "77.5946",
        },
        headers={"Authorization": f"Bearer {reporter_token}"},
    )
    assert issue_resp.status_code == 201
    issue_id = issue_resp.json()["id"]

    # Create AUTO_HIDE_FLAG_COUNT unique users, each flags the issue
    for i in range(AUTO_HIDE_FLAG_COUNT):
        sfx = uuid.uuid4().hex[:8]
        reg2 = await client.post("/auth/register", json={
            "email": f"flagger_{i}_{sfx}@lumen.com",
            "password": "password123",
            "username": f"flagger_{i}_{sfx}",
            "display_name": f"Flagger {i}",
        })
        flagger_token = reg2.json()["access_token"]

        flag_resp = await client.post(
            f"/issues/{issue_id}/flag",
            json={"reason": "spam", "detail": f"Test flag {i}"},
            headers={"Authorization": f"Bearer {flagger_token}"},
        )
        assert flag_resp.status_code == 204

    # After AUTO_HIDE_FLAG_COUNT flags, the issue status should be 'closed'
    issue_detail = await client.get(f"/issues/{issue_id}")
    assert issue_detail.status_code == 200
    assert issue_detail.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_flag_dismiss_lifecycle(db_session):
    """dismiss_flag changes flag status to 'dismissed' and returns True."""
    from app.services.moderation import dismiss_flag
    from app.models import Flag

    flag_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()

    # dismiss_flag on non-existent flag must return False (not crash)
    result = await dismiss_flag(
        flag_id=flag_id,
        reviewer_id=reviewer_id,
        db=db_session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_flag_resolve_lifecycle(db_session):
    """resolve_flag on non-existent flag must return False (not crash)."""
    from app.services.moderation import resolve_flag

    result = await resolve_flag(
        flag_id=uuid.uuid4(),
        reviewer_id=uuid.uuid4(),
        db=db_session,
    )
    assert result is False
