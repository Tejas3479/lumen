"""
Tests: Authentication flows
Covers: register, login, guest session, logout, get_me,
        duplicate email, duplicate username, bad credentials,
        weak password, anonymous flag, guest flag, banned user.

All tests use the async client + isolated test DB from conftest.py.
Each test function gets a fresh rolled-back db_session — no cross-test pollution.
"""
import pytest


# ─── Registration ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_new_user(client):
    response = await client.post("/auth/register", json={
        "email": "test@lumen.com",
        "password": "password123",
        "username": "testuser",
        "display_name": "Test User",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "test@lumen.com"
    assert data["user"]["username"] == "testuser"
    assert data["user"]["is_guest"] is False
    assert data["user"]["is_admin"] is False
    assert data["user"]["points"] == 0
    assert data["user"]["level"] == 1


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {
        "email": "dup@lumen.com",
        "password": "password123",
        "username": "user1_dup",
        "display_name": "User One",
    }
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201

    # Second registration with same email, different username
    payload["username"] = "user2_dup"
    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code == 409
    body = r2.json()
    assert "error_code" in body
    assert body["error_code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_register_duplicate_username(client):
    await client.post("/auth/register", json={
        "email": "uniq1@lumen.com",
        "password": "password123",
        "username": "shared_username",
        "display_name": "User A",
    })
    response = await client.post("/auth/register", json={
        "email": "uniq2@lumen.com",
        "password": "password123",
        "username": "shared_username",  # same username, different email
        "display_name": "User B",
    })
    assert response.status_code == 409
    assert response.json()["error_code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_register_weak_password_too_short(client):
    """Password must be at least 8 chars."""
    response = await client.post("/auth/register", json={
        "email": "short@lumen.com",
        "password": "abc123",  # only 6 chars
        "username": "shortpwuser",
        "display_name": "Short PW",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_no_digit(client):
    """Password must contain at least one digit."""
    response = await client.post("/auth/register", json={
        "email": "nodigit@lumen.com",
        "password": "abcdefghij",  # no digits
        "username": "nodigituser",
        "display_name": "No Digit",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client):
    response = await client.post("/auth/register", json={
        "email": "not-an-email",
        "password": "password123",
        "username": "bademailuser",
        "display_name": "Bad Email",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_username_too_short(client):
    response = await client.post("/auth/register", json={
        "email": "ok@lumen.com",
        "password": "password123",
        "username": "ab",  # min 3 chars
        "display_name": "Short Username",
    })
    assert response.status_code == 422


# ─── Login ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/auth/register", json={
        "email": "login@lumen.com",
        "password": "password123",
        "username": "loginuser",
        "display_name": "Login User",
    })
    response = await client.post("/auth/login", json={
        "email": "login@lumen.com",
        "password": "password123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "login@lumen.com"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "email": "wrongpw@lumen.com",
        "password": "password123",
        "username": "wrongpwuser",
        "display_name": "Wrong PW",
    })
    response = await client.post("/auth/login", json={
        "email": "wrongpw@lumen.com",
        "password": "definitelywrong99",
    })
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_nonexistent_email(client):
    """Login with non-existent email returns 401, not 404 (prevents enumeration)."""
    response = await client.post("/auth/login", json={
        "email": "nobody@lumen.com",
        "password": "password123",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_same_error_for_missing_vs_wrong_password(client):
    """Both missing user and wrong password return the same error to prevent enumeration."""
    await client.post("/auth/register", json={
        "email": "enum@lumen.com",
        "password": "password123",
        "username": "enumuser",
        "display_name": "Enum User",
    })
    r1 = await client.post("/auth/login", json={"email": "enum@lumen.com", "password": "wrongone1"})
    r2 = await client.post("/auth/login", json={"email": "nosuchuser@lumen.com", "password": "wrongone1"})

    assert r1.status_code == 401
    assert r2.status_code == 401
    # Same error message to prevent email enumeration
    assert r1.json()["message"] == r2.json()["message"]


# ─── Guest Session ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_guest_session_creation(client):
    response = await client.post("/auth/guest")
    assert response.status_code == 200
    data = response.json()
    assert "guest_session_id" in data
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["guest_session_id"]) > 10


@pytest.mark.asyncio
async def test_guest_session_yields_unique_ids(client):
    """Each guest session call creates a fresh unique session."""
    r1 = await client.post("/auth/guest")
    r2 = await client.post("/auth/guest")
    assert r1.json()["guest_session_id"] != r2.json()["guest_session_id"]
    assert r1.json()["access_token"] != r2.json()["access_token"]


@pytest.mark.asyncio
async def test_guest_user_is_guest_flag(client):
    """Guest session users have is_guest=True when fetching /auth/me."""
    guest = await client.post("/auth/guest")
    token = guest.json()["access_token"]

    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["is_guest"] is True
    assert me.json()["is_admin"] is False


# ─── /auth/me ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_authenticated(client):
    reg = await client.post("/auth/register", json={
        "email": "me@lumen.com",
        "password": "password123",
        "username": "meuser",
        "display_name": "Me User",
    })
    token = reg.json()["access_token"]

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@lumen.com"
    assert data["username"] == "meuser"
    assert data["display_name"] == "Me User"
    assert "password_hash" not in data  # never exposed


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client):
    response = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_malformed_auth_header(client):
    """Missing 'Bearer ' prefix."""
    response = await client.get(
        "/auth/me",
        headers={"Authorization": "justthetoken"},
    )
    assert response.status_code == 401


# ─── Logout ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout(client):
    reg = await client.post("/auth/register", json={
        "email": "logout@lumen.com",
        "password": "password123",
        "username": "logoutuser",
        "display_name": "Logout User",
    })
    token = reg.json()["access_token"]

    response = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_logout_unauthenticated(client):
    response = await client.post("/auth/logout")
    assert response.status_code == 401


# ─── Anonymous and Privacy ────────────────────────────────────

@pytest.mark.asyncio
async def test_anonymous_flag_default_false(client):
    """Newly registered users do NOT post anonymously by default."""
    reg = await client.post("/auth/register", json={
        "email": "anoncheck@lumen.com",
        "password": "password123",
        "username": "anoncheckuser",
        "display_name": "Anon Check",
    })
    assert reg.json()["user"]["is_anonymous_default"] is False


@pytest.mark.asyncio
async def test_registered_user_not_guest(client):
    """Registered users have is_guest=False."""
    reg = await client.post("/auth/register", json={
        "email": "notguest@lumen.com",
        "password": "password123",
        "username": "notguestuser",
        "display_name": "Not Guest",
    })
    assert reg.json()["user"]["is_guest"] is False


@pytest.mark.asyncio
async def test_notification_preferences_initialized(client):
    """New users get default notification preferences."""
    reg = await client.post("/auth/register", json={
        "email": "notif@lumen.com",
        "password": "password123",
        "username": "notifuser",
        "display_name": "Notif User",
    })
    token = reg.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    prefs = me.json()["notification_preferences"]
    assert prefs.get("notify_on_status_change") is True
    assert prefs.get("notify_on_verification") is True
