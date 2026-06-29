# Lumen — Testing

## Test Strategy Overview

Lumen uses a layered testing strategy:

| Layer | Tool | Scope | Coverage Target |
|-------|------|-------|----------------|
| **Backend Unit** | pytest + pytest-asyncio | Service functions, utilities, edge cases | ≥ 70% overall |
| **Backend Integration** | pytest + httpx AsyncClient | API endpoints, DB interactions, auth flows | ≥ 90% on critical paths |
| **Frontend E2E** | Playwright | Full user flows in a real browser | Key user journeys |

**Philosophy:**
- Critical paths (auth, issue creation, verification, admin status changes) must have ≥ 90% line coverage.
- Edge cases (spam detection, duplicate detection, geo-utils) have dedicated focused test files.
- E2E tests focus on user journeys, not implementation details — they test what the user sees and does.

---

## Backend Unit Test Inventory

All unit tests are in `backend/tests/`. Each test file maps to a service or utility module.

### `test_health.py`
**Scope:** API health endpoints  
**Tests:**
- `GET /health` returns 200 with `status: "healthy"`
- `GET /health/ready` returns database connectivity check

### `test_auth.py`
**Scope:** Authentication service (`auth_service.py`, `/auth` routes)  
**Tests:**
- Register: success with valid payload
- Register: 409 conflict on duplicate email
- Register: 409 conflict on duplicate username
- Register: 422 on weak password (< 8 chars)
- Login: success with correct credentials → JWT returned
- Login: 401 on wrong password
- Login: 401 on banned account
- Guest session: creates guest user + returns JWT
- `GET /auth/me`: returns current user with valid JWT
- `GET /auth/me`: 401 with no JWT
- `PATCH /auth/me/settings`: updates display_name, pseudonym, privacy_settings
- Logout: 204 with valid JWT

### `test_issues.py`
**Scope:** Issue creation, listing, detail, update, delete (`issues.py`, `issue_service.py`)  
**Tests:**
- Create issue: 201 with all required fields
- Create issue: offline_draft_id idempotency (duplicate key → return existing)
- Create issue: anonymous issue (reporter_id null in public response)
- Create issue: emergency issue emits emergency_alert event
- List issues: pagination (page, per_page)
- List issues: filter by status, category, severity, ward
- Nearby issues: radius filter, distance ordering
- Check duplicates: returns has_duplicates=true when similar issue nearby
- Get issue detail: increments view_count
- Update issue: reporter can edit title/description
- Update issue: non-reporter gets 403
- Delete issue: admin hard-delete
- Delete issue: reporter closes own issue
- Status change: valid transitions accepted
- Status change: invalid transitions rejected with 422
- Assign issue: sets status to assigned, deactivates prior assignments

### `test_verification.py`
**Scope:** Verification service (`verification_service.py`, `/issues/{id}/verify`)  
**Tests:**
- Hard verify: within 100m → success, trust_weight=1.0, +25 points
- Hard verify: beyond 100m → PROXIMITY_REQUIRED error
- Soft verify: no coordinates needed → success, trust_weight=0.5, +10 points
- Self-verify: reporter cannot verify own issue → 403
- Double-verify: same user cannot verify twice → 409
- Auto-upgrade: weighted_score ≥ 2.0 → status transitions to `verified`
- Terminal state guard: cannot verify resolved issue
- First-responder bonus: first verifier gets +15 extra points

### `test_comments.py`
**Scope:** Comment CRUD (`comments.py`)  
**Tests:**
- Create comment: success, emits comment_added event
- Create comment: invalid issue_id → 404
- Create reply: parent_comment_id threading works
- List comments: official comments appear first
- Update comment: author can edit
- Update comment: non-author gets 403
- Delete comment: soft delete (is_deleted=True, content replaced)
- Delete comment: admin can delete any comment

### `test_ai.py`
**Scope:** AI categoriser, routes (`ai_categorizer.py`, `/ai` routes)  
**Tests:**
- AI status: returns cached result from Redis (source="cache")
- AI status: returns DB result when Redis empty (source="database")
- AI status: returns pending when AI not yet run
- AI feedback: correction logged in IssueAuditLog
- AI feedback: corrected_category resolves to category_id in DB
- AI recategorize: dispatches new Celery task
- Response parser: handles markdown-wrapped JSON
- Response parser: handles invalid JSON → safe default
- Response parser: coerces invalid category to "other"

### `test_verification.py` (also covers geo_utils)
See `test_geo_utils.py` for isolated Haversine tests.

### `test_geo_utils.py`
**Scope:** `geo_utils.py` (Haversine, ward lookup, coordinate validation)  
**Tests:**
- is_within_radius: 50m → True
- is_within_radius: 150m → False at 100m threshold
- is_within_radius: 0m (same point) → True
- is_within_radius: Haversine accuracy on known coordinate pairs
- Coordinate validation: latitude out of range → ValueError
- Coordinate validation: longitude out of range → ValueError

### `test_spam_detection.py`
**Scope:** Spam detector (`spam_detector.py`)  
**Tests:**
- Short title blocked (< 5 chars)
- Duplicate title from same user within 1 hour → spam
- Profanity filter match → spam
- Rate limit: > 5 issues in 10 minutes → spam
- Gibberish detection: high consonant ratio → spam
- Legitimate issue passes all checks
- Anonymous issue: spam check still applied

### `test_duplicate_detection.py`
**Scope:** Duplicate detector (`duplicate_detector.py`)  
**Tests:**
- Same title, same location → high similarity, returned as duplicate
- Similar title, different ward → no duplicate
- Exact match → duplicate_strength="exact"
- Fuzzy match (TF-IDF similarity > 0.7) → returned as potential duplicate
- Resolved issues not returned as duplicates
- Distance calculation: issue 50m away returned, 300m away excluded

### `test_admin_flows.py`
**Scope:** Admin routes (`admin.py`)  
**Tests:**
- Admin queue: returns paginated results with emergency issues first
- Admin queue: filter combinations work
- Bulk update: all valid → updated list returned
- Bulk update: one invalid transition → error collected, others proceed
- List users: search by email, username, display_name
- Moderate user: ban, unban, promote to official
- Flag queue: paginated pending flags
- Review flag: dismissed clears hide; reviewed keeps hide
- Export CSV: correct headers and data format
- Export JSON: valid JSON array
- Non-admin cannot access admin routes → 403

### `test_offline_sync.py`
**Scope:** Offline sync route and draft model (`offline.py`, `OfflineDraft`)  
**Tests:**
- Sync: new draft → issue created, draft marked synced
- Sync: duplicate key (already synced) → skipped, existing issue_id returned
- Sync: invalid draft (missing required fields) → failed entry, batch continues
- Sync: batch of 3 drafts (1 new, 1 duplicate, 1 invalid) → correct classification
- Sync: unauthenticated user (guest) → issue created with null reporter_id
- Draft record: idempotency key uniqueness enforced

### `test_media.py`
**Scope:** Media upload, retrieval, deletion (`media.py`, image processing utils)  
**Tests:**
- Upload: valid JPEG accepted, thumbnail generated
- Upload: PNG accepted
- Upload: WebP accepted
- Upload: SVG rejected (not in allowed list)
- Upload: file size > MAX_PHOTO_SIZE_MB → 422
- Upload: MIME sniff (detect spoofed Content-Type)
- Upload: linked to issue_id → media.issue_id set
- Get media: metadata returned
- Get media: 404 on unknown id
- Delete media: reporter can delete own issue media
- Delete media: non-reporter gets 403
- Delete media: admin can delete any media
- Delete media: file removed from disk

### `test_sockets.py`
**Scope:** Socket.IO event emission (`sockets/events.py`)  
**Tests:**
- emit_new_issue: event fired with correct payload
- emit_status_update: room targeting by issue_id
- emit_emergency_alert: broadcast to all
- emit_verification_update: correct verification data
- emit_comment_added: issue room targeting
- Redis subscriber: publishes event to connected clients

### `test_full_lifecycle.py`
**Scope:** End-to-end integration test covering the complete issue lifecycle  
**Test flow:**
1. Register user
2. Create issue → 201
3. Verify issue (hard) → auto-upgrade if weighted_score ≥ 2.0
4. Official assigns → status: assigned
5. Official marks in_progress → status: in_progress
6. Official resolves → status: resolved
7. Reporter confirms resolution → is_resolved: true
8. Reporter disputes resolution → 3 disputes → status: disputed
9. Official re-resolves → status: resolved
10. Issue closed

---

## Backend Integration Test Inventory

Integration tests use `pytest` with `httpx.AsyncClient` against a test database (separate PostgreSQL database seeded fresh per test session).

**Test database:** `lumen_test` (configured via `DATABASE_URL_TEST` env var or `TEST_DATABASE_URL` in `pytest.ini`).

**Configuration (`pytest.ini`):**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
env_files = .env.test
```

**Fixtures (`conftest.py`):**
```python
@pytest.fixture(scope="session")
async def engine():
    return create_async_engine(settings.test_database_url)

@pytest.fixture(autouse=True)
async def clean_db(engine):
    # Drop + recreate all tables between tests using Alembic
    ...

@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def auth_headers(client):
    # Register + login, return {"Authorization": "Bearer <token>"}
    ...
```

---

## Frontend E2E Test Inventory

E2E tests use Playwright and are located in `frontend/tests/e2e/`.

### `report_flow.spec.ts`

**Test Suite: Report Issue Flow**
1. `should complete full report flow` — Opens app, clicks FAB, fills form, submits, sees success toast
2. `should close report dialog on cancel` — Opens modal, presses Escape, modal disappears

**Test Suite: Offline Behavior**
3. `should show offline banner when network is down` — Sets context offline, checks for offline indicator
4. `should allow offline draft creation` — Opens form while offline, verifies dialog appears

**Test Suite: Accessibility**
5. `skip to main content link is present and functional` — Checks `href="#main-content"`
6. `report form is keyboard navigable` — Opens form, tabs through 3 elements, dialog remains open
7. `map has accessible label` — `aria-label="Community issue map"` is visible
8. `FAB button has accessible label` — `aria-label="Report a new issue"` attribute present

**Test Suite: Navigation**
9. `page title is set` — `document.title` matches `/Lumen/i`
10. `home page loads without errors` — No critical console errors on load

---

## Coverage Targets

| Module | Target | Critical Path |
|--------|--------|---------------|
| `auth_service.py` | ≥ 80% | ✓ 90%+ |
| `issue_service.py` | ≥ 80% | ✓ 90%+ |
| `verification_service.py` | ≥ 90% | ✓ 90%+ |
| `spam_detector.py` | ≥ 85% | |
| `duplicate_detector.py` | ≥ 85% | |
| `gamification.py` | ≥ 75% | |
| `geo_utils.py` | ≥ 95% | ✓ |
| `ai_categorizer.py` | ≥ 70% | |
| `routes/admin.py` | ≥ 80% | |
| `routes/offline.py` | ≥ 90% | ✓ 90%+ |
| **Overall backend** | **≥ 70%** | |

---

## How to Run Tests

### Backend Tests

```bash
# All tests
cd backend
pytest

# With coverage report
pytest --cov=app --cov-report=html --cov-report=term

# Specific test file
pytest tests/test_issues.py -v

# Specific test
pytest tests/test_verification.py::test_hard_verification_within_radius -v

# Run tests matching a keyword
pytest -k "spam" -v

# Parallel execution (requires pytest-xdist)
pytest -n auto

# Fast fail on first failure
pytest -x
```

### Frontend E2E Tests

```bash
# Install Playwright browsers (first time)
cd frontend
npx playwright install --with-deps

# Run all E2E tests (requires running app)
npm run test:e2e

# Run against dev server (auto-starts)
npx playwright test --config playwright.config.ts

# Headed mode (visible browser)
npx playwright test --headed

# Specific test file
npx playwright test tests/e2e/report_flow.spec.ts

# Debug mode
npx playwright test --debug
```

### Playwright Config (`playwright.config.ts`)

```typescript
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
  },
});
```

---

## Seed Data for Demo

The `seed_data.py` script populates the database with realistic demo data for testing and demonstration:

```bash
# Run against local database
cd backend
python seed_data.py

# Run inside Docker
docker compose exec lumen-api python seed_data.py
```

**Seeded data:**
- **Categories** (6): pothole, water_leakage, streetlight, garbage, drainage, other
- **Badges** (10): first_report, reporter_5, reporter_25, verifier_10, streak_7, streak_30, first_responder, resolver, century, champion
- **Users**: 1 admin, 3 officials (different departments), 20 citizen accounts
- **Issues**: 200 issues across all categories, statuses, wards, and severities
- **Verifications**: 300+ hard and soft verifications
- **Comments**: 150+ comments with replies
- **Votes**: 500+ support votes
- **Gamification**: Points, levels, badges assigned to demo users
- **Predictive hotspots**: 5 pre-computed hotspot clusters

The seed script is idempotent on categories and badges (uses upsert logic). Running it twice does not create duplicate categories.
