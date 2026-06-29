import pytest
import uuid
from sqlalchemy import select
from app.models import User, Issue, Comment, Vote, UserBadge, LeaderboardPoints
from app.services.auth_service import register_user
from app.services.issue_service import create_issue
from app.schemas import IssueCreate

@pytest.mark.asyncio
async def test_user_deletion_and_set_null(db_session):
    # 1. Create a registered user
    user, _ = await register_user(
        email="test_deletion@example.com",
        password="Password123",
        username="test_deletion_user",
        display_name="Test Deletion User",
        db=db_session
    )
    user_id = user.id

    # 2. Create a category
    from app.models import Category
    cat = Category(name="pothole_test_del", display_name="Pothole Test Del")
    db_session.add(cat)
    await db_session.flush()

    # 3. Create an issue reported by the user
    payload = IssueCreate(
        title="Pothole on Main Road",
        description="Huge pothole causing traffic jam",
        latitude=12.9716,
        longitude=77.5946,
        category_id=cat.id,
        severity="high",
        is_emergency=False,
    )
    issue = await create_issue(payload=payload, db=db_session, reporter=user)
    await db_session.flush()
    issue_id = issue.id
    assert issue.reporter_id == user_id

    # 4. Create a comment by the user
    comment = Comment(
        issue_id=issue_id,
        user_id=user_id,
        content="This is indeed dangerous!"
    )
    db_session.add(comment)
    
    # 5. Create a vote by the user
    vote = Vote(
        issue_id=issue_id,
        user_id=user_id,
        vote_type="support"
    )
    db_session.add(vote)
    
    # 6. Create points log (should cascade delete)
    points_log = LeaderboardPoints(
        user_id=user_id,
        action="report",
        points=10,
        issue_id=issue_id
    )
    db_session.add(points_log)
    
    # 7. Create user badge (should cascade delete)
    from app.models import Badge
    badge = Badge(
        name="pothole_warrior_del",
        display_name="Pothole Warrior Del",
        description="Reported first pothole",
        icon="shield",
        category="reporting"
    )
    db_session.add(badge)
    await db_session.flush()
    
    user_badge = UserBadge(
        user_id=user_id,
        badge_id=badge.id
    )
    db_session.add(user_badge)
    await db_session.flush()

    # Commit transactions
    await db_session.commit()

    # 8. Delete the user record
    await db_session.delete(user)
    await db_session.commit()

    # 9. Verify that the user no longer exists
    res_user = await db_session.execute(select(User).where(User.id == user_id))
    assert res_user.scalar_one_or_none() is None

    # 10. Verify that issue.reporter_id has been nullified (SET NULL)
    res_issue = await db_session.execute(select(Issue).where(Issue.id == issue_id))
    updated_issue = res_issue.scalar_one()
    assert updated_issue.reporter_id is None

    # 11. Verify comment.user_id has been nullified (SET NULL)
    res_comment = await db_session.execute(select(Comment).where(Comment.issue_id == issue_id))
    updated_comment = res_comment.scalar_one()
    assert updated_comment.user_id is None

    # 12. Verify vote.user_id has been nullified (SET NULL)
    res_vote = await db_session.execute(select(Vote).where(Vote.issue_id == issue_id))
    updated_vote = res_vote.scalar_one()
    assert updated_vote.user_id is None

    # 13. Verify that user badge and points log were deleted (CASCADE)
    res_points = await db_session.execute(select(LeaderboardPoints).where(LeaderboardPoints.user_id == user_id))
    assert res_points.scalar_one_or_none() is None
    
    res_badge = await db_session.execute(select(UserBadge).where(UserBadge.user_id == user_id))
    assert res_badge.scalar_one_or_none() is None

    # Clean up test records
    await db_session.delete(updated_issue)
    await db_session.delete(cat)
    await db_session.delete(badge)
    await db_session.commit()
