# Lumen — API Reference

**Base URL:** `http://localhost:8000` (development) | `https://api.lumen.example.com` (production)  
**Authentication:** Bearer token — `Authorization: Bearer <jwt>`  
**Content-Type:** `application/json` for JSON endpoints; `multipart/form-data` for file uploads  
**API version:** v1 (no prefix — all routes are at root level)

---

## Authentication

### POST /auth/register

Create a new citizen account.

| | |
|--|--|
| **Auth Required** | No |
| **Content-Type** | application/json |

**Request Body:**
```json
{
  "email": "priya@example.com",
  "password": "securepassword123",
  "username": "priya_s",
  "display_name": "Priya S."
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `email` | string | Valid email, unique |
| `password` | string | Min 8 chars, must contain ≥ 1 digit |
| `username` | string | 3–64 chars, alphanumeric + underscores, unique |
| `display_name` | string | 1–128 chars |

**Response: 201 Created**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "priya@example.com",
    "username": "priya_s",
    "display_name": "Priya S.",
    "is_admin": false,
    "is_official": false,
    "is_banned": false,
    "points": 0,
    "level": 1,
    "streak_days": 0
  }
}
```

**Errors:** `409 CONFLICT` (email/username taken), `422 UNPROCESSABLE`

---

### POST /auth/login

Authenticate with email and password.

| | |
|--|--|
| **Auth Required** | No |
| **Content-Type** | application/json |

**Request Body:**
```json
{
  "email": "priya@example.com",
  "password": "securepassword123"
}
```

**Response: 200 OK** — same as `/auth/register` (TokenResponse)

**Errors:** `401 UNAUTHORIZED` (wrong credentials or banned account)

---

### POST /auth/guest

Create a guest session (no account required).

| | |
|--|--|
| **Auth Required** | No |
| **Content-Type** | application/json |
| **Request Body** | None |

**Response: 200 OK**
```json
{
  "guest_session_id": "uuid",
  "access_token": "eyJ...",
  "token_type": "bearer",
  "message": "Guest session created. You can report issues without an account."
}
```

---

### POST /auth/logout

Logout (stateless — client discards JWT). Server logs the event.

| | |
|--|--|
| **Auth Required** | Yes |
| **Request Body** | None |

**Response: 204 No Content**

---

### GET /auth/me

Get current authenticated user's profile.

| | |
|--|--|
| **Auth Required** | Yes |

**Response: 200 OK** — UserMe object (same structure as register response `user` field)

**Errors:** `401 UNAUTHORIZED`

---

### GET /auth/me/settings

Get current user's full profile including notification and privacy preferences.

| | |
|--|--|
| **Auth Required** | Yes |

**Response: 200 OK** — UserMe object

---

### PATCH /auth/me/settings

Update user profile and preferences.

| | |
|--|--|
| **Auth Required** | Yes |
| **Content-Type** | application/json |

**Request Body (all fields optional):**
```json
{
  "display_name": "Priya Sharma",
  "pseudonym": "CivicHero_42",
  "is_anonymous_default": false,
  "privacy_settings": {
    "show_on_leaderboard": true,
    "mobility_limited": false
  },
  "notification_preferences": {
    "status_changes": true,
    "verifications": true,
    "comments": false,
    "email_weekly": false
  }
}
```

**Response: 200 OK** — Updated UserMe object

---

## Issues

### POST /issues

Create a new civic issue report. Accepts multipart form data.

| | |
|--|--|
| **Auth Required** | Optional (anonymous supported) |
| **Content-Type** | multipart/form-data |

**Request Form Fields:**

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | ✓ | 5–256 chars |
| `description` | string | ✓ | 10–5000 chars |
| `latitude` | float | ✓ | -90 to 90 |
| `longitude` | float | ✓ | -180 to 180 |
| `address` | string | — | Max 512 chars |
| `ward` | string | — | Max 128 chars |
| `severity` | string | — | `low`/`medium`/`high`/`critical` (default: `medium`) |
| `is_anonymous` | bool | — | Default: false |
| `is_emergency` | bool | — | Default: false |
| `category_id` | UUID string | — | Valid category UUID |
| `offline_draft_id` | string | — | Idempotency key for offline sync |
| `files` | File[] | — | JPEG, PNG, WebP, MP4, MOV (up to limit) |

**Response: 201 Created** — IssueOut object

```json
{
  "id": "uuid",
  "title": "Large pothole near Kalyani Nagar junction",
  "description": "Deep pothole causing tyre damage...",
  "latitude": 18.5204,
  "longitude": 73.8567,
  "address": "Kalyani Nagar, Pune",
  "ward": "Ward 12",
  "severity": "high",
  "status": "reported",
  "is_anonymous": false,
  "is_emergency": false,
  "vote_count": 0,
  "verification_count": 0,
  "view_count": 0,
  "ai_category": null,
  "ai_severity": null,
  "ai_confidence": null,
  "ai_explanation": null,
  "ai_summary": null,
  "category": {"id": "uuid", "name": "pothole", "display_name": "Pothole", "icon": "🕳️"},
  "reporter": {"id": "uuid", "display_name": "Priya S.", "pseudonym": null},
  "media": [],
  "status_history": [{"from_status": null, "to_status": "reported", "changed_at": "2024-01-15T10:30:00Z"}],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "resolved_at": null
}
```

**Errors:** `400 SPAM_DETECTED`, `409 CONFLICT` (idempotency match returns existing issue), `422 UNPROCESSABLE`

---

### GET /issues

Paginated issue list with optional filters.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number (≥ 1) |
| `per_page` | int | 20 | Items per page (1–100) |
| `status` | string | — | Filter by status |
| `category` | string | — | Filter by category name |
| `severity` | string | — | Filter by severity |
| `ward` | string | — | Filter by ward (partial match) |
| `is_emergency` | bool | — | Filter emergencies only |
| `sort_by` | string | `created_at` | Sort field |
| `sort_dir` | string | `desc` | `asc` or `desc` |

**Response: 200 OK**
```json
{
  "items": [/* IssueOut[] */],
  "total": 150,
  "page": 1,
  "per_page": 20,
  "pages": 8
}
```

---

### GET /issues/nearby

Issues within a radius of the given coordinates.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `lat` | float | ✓ | -90 to 90 | Centre latitude |
| `lng` | float | ✓ | -180 to 180 | Centre longitude |
| `radius` | float | — | 100–50,000 (default: 2000) | Radius in metres |
| `limit` | int | — | 1–200 (default: 50) | Maximum results |

**Response: 200 OK** — `IssueOut[]` sorted by distance (emergency issues first)

---

### GET /issues/check-duplicates

Pre-submit duplicate check. Called before form submission.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `title` | string | ✓ (min 5 chars) |
| `description` | string | ✓ (min 10 chars) |
| `latitude` | float | ✓ |
| `longitude` | float | ✓ |
| `category_id` | UUID string | — |

**Response: 200 OK**
```json
{
  "has_duplicates": true,
  "duplicates": [
    {
      "issue_id": "uuid",
      "title": "Pothole near Kalyani Nagar",
      "status": "verified",
      "distance_meters": 45.2,
      "similarity_score": 0.87,
      "duplicate_strength": "high"
    }
  ],
  "message": "Found 1 similar issue(s) nearby. Consider supporting an existing report instead."
}
```

---

### GET /issues/{issue_id}

Full issue detail with media, status history, verifications, and comments.

| | |
|--|--|
| **Auth Required** | No |
| **Path Param** | `issue_id` — UUID |

**Response: 200 OK** — Full IssueOut object (increments `view_count`)

**Errors:** `404 NOT_FOUND`

---

### PATCH /issues/{issue_id}

Update issue title, description, category, or severity. Reporter or admin only.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `issue_id` — UUID |

**Request Body (all optional):**
```json
{
  "title": "Updated title",
  "description": "Updated description",
  "category_id": "uuid",
  "severity": "critical"
}
```

**Response: 200 OK** — Updated IssueOut

**Errors:** `403 FORBIDDEN` (not reporter or admin), `404 NOT_FOUND`

---

### DELETE /issues/{issue_id}

Reporters close their own issue (status → closed). Admins hard-delete.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `issue_id` — UUID |

**Response: 204 No Content**

**Errors:** `403 FORBIDDEN`, `404 NOT_FOUND`

---

### PATCH /issues/{issue_id}/status

Change issue status. Officials and admins only.

| | |
|--|--|
| **Auth Required** | Yes (official or admin) |
| **Path Param** | `issue_id` — UUID |

**Request Body:**
```json
{
  "status": "in_progress",
  "note": "Repair crew dispatched",
  "is_public": true
}
```

**Valid status values:** `reported`, `verified`, `assigned`, `in_progress`, `resolved`, `closed`, `disputed`

**Response: 200 OK** — Updated IssueOut

**Errors:** `403 FORBIDDEN`, `404 NOT_FOUND`, `422 INVALID_TRANSITION`

---

### POST /issues/{issue_id}/assign

Assign issue to an official. Sets status to `assigned`.

| | |
|--|--|
| **Auth Required** | Yes (official or admin) |
| **Path Param** | `issue_id` — UUID |

**Request Body:**
```json
{
  "assigned_to": "uuid",
  "department": "Roads & Infrastructure",
  "due_date": "2024-01-22T00:00:00Z",
  "note": "Priority repair — school zone"
}
```

**Response: 200 OK** — Updated IssueOut

---

### POST /issues/{issue_id}/flag

Flag an issue for moderation. One flag per user per issue.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `issue_id` — UUID |

**Request Body:**
```json
{
  "reason": "spam",
  "detail": "This is an obvious duplicate of issue #1234"
}
```

**Valid reasons:** `spam`, `duplicate`, `inappropriate`, `resolved`, `wrong_location`

**Response: 204 No Content**

**Errors:** `409 CONFLICT` (already flagged), `404 NOT_FOUND`

---

### POST /issues/{issue_id}/verify

Community verification — hard or soft.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `issue_id` — UUID |

**Request Body:**
```json
{
  "verification_type": "hard",
  "latitude": 18.5206,
  "longitude": 73.8570,
  "comment": "I walked past this pothole this morning"
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `verification_type` | ✓ | `"hard"` or `"soft"` |
| `latitude` | For hard only | User's current GPS lat |
| `longitude` | For hard only | User's current GPS lng |
| `comment` | — | Optional text |

**Response: 201 Created**
```json
{
  "id": "uuid",
  "issue_id": "uuid",
  "user_id": "uuid",
  "verification_type": "hard",
  "trust_weight": 1.0,
  "distance_meters": 45.2,
  "comment": "Walked past this morning",
  "created_at": "2024-01-15T11:00:00Z"
}
```

**Errors:** `403 FORBIDDEN` (self-verify), `409 CONFLICT` (already verified), `422 PROXIMITY_REQUIRED` (hard verify too far)

---

### POST /issues/{issue_id}/support

"I see this too" vote. One per user/session.

| | |
|--|--|
| **Auth Required** | Optional |
| **Path Param** | `issue_id` — UUID |

**Request Body:**
```json
{
  "vote_type": "support",
  "duplicate_of": null
}
```

**Response: 201 Created** — VoteOut

**Errors:** `409 CONFLICT` (already voted)

---

### POST /issues/{issue_id}/resolution-feedback

Citizen confirms or disputes a resolution.

| | |
|--|--|
| **Auth Required** | Optional |
| **Path Param** | `issue_id` — UUID |

**Request Body:**
```json
{
  "is_resolved": false,
  "comment": "The pothole was patched but has already re-opened"
}
```

**Response: 201 Created**
```json
{
  "id": "uuid",
  "issue_id": "uuid",
  "is_resolved": false,
  "comment": "...",
  "dispute_triggers_reopen": true,
  "created_at": "2024-01-22T09:00:00Z"
}
```

**Errors:** `422 VALIDATION_ERROR` (issue not in resolved/disputed state)

---

## Comments

### POST /comments

Add a comment or threaded reply to an issue.

| | |
|--|--|
| **Auth Required** | Yes |

**Request Body:**
```json
{
  "issue_id": "uuid",
  "content": "I can confirm this pothole is dangerous — my tyre burst here.",
  "parent_comment_id": null
}
```

**Response: 201 Created** — CommentOut (includes user details and any replies)

---

### GET /comments

List top-level comments for an issue. Replies nested under parent.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `issue_id` | UUID | ✓ |

**Response: 200 OK** — `CommentOut[]` (official comments first, then pinned, then by created_at)

---

### PATCH /comments/{comment_id}

Edit comment content. Author or admin only.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `comment_id` — UUID |

**Request Body:**
```json
{
  "content": "Corrected comment text"
}
```

**Response: 200 OK** — Updated CommentOut

**Errors:** `403 FORBIDDEN`, `404 NOT_FOUND`

---

### DELETE /comments/{comment_id}

Soft-delete a comment. Author or admin only.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `comment_id` — UUID |

**Response: 204 No Content**

**Errors:** `403 FORBIDDEN`, `404 NOT_FOUND`

---

## AI

### GET /ai/status/{issue_id}

Poll AI categorisation result.

| | |
|--|--|
| **Auth Required** | No |
| **Path Param** | `issue_id` — UUID |

**Response: 200 OK (result available)**
```json
{
  "issue_id": "uuid",
  "ai_category": "pothole",
  "ai_severity": "high",
  "ai_confidence": 0.91,
  "ai_explanation": "Road surface shows a 45cm depression...",
  "ai_summary": "Large pothole on road",
  "source": "cache"
}
```

**Response: 200 OK (pending)**
```json
{
  "issue_id": "uuid",
  "status": "pending",
  "message": "AI categorization is still processing. Check back in a few seconds."
}
```

**Errors:** `404 NOT_FOUND`

---

### POST /ai/feedback

Log user correction of AI suggestion (RLHF-lite).

| | |
|--|--|
| **Auth Required** | Optional |

**Request Body:**
```json
{
  "issue_id": "uuid",
  "corrected_category": "water_leakage",
  "corrected_severity": "critical",
  "user_comment": "This is not a pothole, it's a burst water main"
}
```

**Response: 200 OK**
```json
{
  "status": "correction_logged",
  "issue_id": "uuid",
  "message": "Thank you for the correction. This helps improve future AI suggestions."
}
```

---

### GET /ai/categorize/{issue_id}

Re-run AI categorisation on an existing issue.

| | |
|--|--|
| **Auth Required** | No |
| **Path Param** | `issue_id` — UUID |

**Response: 200 OK**
```json
{
  "status": "queued",
  "issue_id": "uuid",
  "message": "AI re-categorization started. Result will arrive via WebSocket or GET /ai/status/{id}."
}
```

**Errors:** `404 NOT_FOUND`

---

## Gamification

### GET /gamification/leaderboard

Paginated leaderboard.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Default | Values |
|-------|------|---------|--------|
| `period` | string | `all_time` | `all_time`, `monthly`, `weekly` |
| `page` | int | 1 | ≥ 1 |
| `per_page` | int | 25 | 1–50 |

**Response: 200 OK**
```json
{
  "items": [
    {
      "rank": 1,
      "user_id": "uuid",
      "display_name": "Priya S.",
      "pseudonym": null,
      "points": 1450,
      "level": 5,
      "badge_count": 7,
      "issues_resolved_count": 12,
      "streak_days": 23
    }
  ],
  "total": 256,
  "page": 1,
  "per_page": 25,
  "pages": 11,
  "period": "all_time"
}
```

---

### GET /gamification/me

Current user's full gamification stats.

| | |
|--|--|
| **Auth Required** | Yes |

**Response: 200 OK**
```json
{
  "user_id": "uuid",
  "display_name": "Priya S.",
  "pseudonym": null,
  "points": 1450,
  "level": 5,
  "points_to_next_level": 50,
  "streak_days": 23,
  "issues_reported": 45,
  "verifications": 67,
  "issues_resolved": 12,
  "badges": [
    {
      "badge": {"id": "uuid", "name": "first_report", "display_name": "First Report", "icon": "📍"},
      "earned_at": "2024-01-10T08:00:00Z"
    }
  ]
}
```

---

### GET /gamification/users/{user_id}

Another user's public gamification profile.

| | |
|--|--|
| **Auth Required** | No |
| **Path Param** | `user_id` — UUID |

**Response: 200 OK** — Same structure as `/gamification/me` (pseudonym shown instead of display_name if user is anonymous)

**Errors:** `404 NOT_FOUND`

---

### GET /gamification/badges

Full badge catalogue.

| | |
|--|--|
| **Auth Required** | No |

**Response: 200 OK** — `Badge[]`
```json
[
  {
    "id": "uuid",
    "name": "first_report",
    "display_name": "First Report",
    "description": "Reported your first civic issue",
    "icon": "📍",
    "category": "reporting",
    "points_required": 0
  }
]
```

---

## Analytics

### GET /analytics/categories

All active categories. Used by report form and admin filters.

| | |
|--|--|
| **Auth Required** | No |

**Response: 200 OK** — `CategoryOut[]`
```json
[
  {"id": "uuid", "name": "pothole", "display_name": "Pothole", "icon": "🕳️", "color": "#EF4444", "avg_resolution_days": 7.0}
]
```

---

### GET /analytics/dashboard

Aggregate statistics for the impact dashboard.

| | |
|--|--|
| **Auth Required** | No |

**Response: 200 OK**
```json
{
  "total_issues": 1250,
  "resolved_this_month": 89,
  "resolution_rate": 71.2,
  "avg_resolution_days": 5.3,
  "issues_by_category": {"pothole": 450, "garbage": 312, "water_leakage": 188},
  "issues_by_status": {"reported": 150, "verified": 87, "in_progress": 43, "resolved": 891},
  "top_wards": [{"ward": "Ward 12", "count": 145}, {"ward": "Ward 7", "count": 112}]
}
```

---

### GET /analytics/eta/{issue_id}

Estimated resolution time for a specific issue.

| | |
|--|--|
| **Auth Required** | No |
| **Path Param** | `issue_id` — UUID |

**Response: 200 OK**
```json
{
  "issue_id": "uuid",
  "estimated_days": 3.5,
  "estimated_resolution_date": "January 18, 2024",
  "confidence": "high",
  "basis": "Based on Pothole average (7 days), adjusted for high severity and assigned status"
}
```

**Errors:** `404 NOT_FOUND`

---

### GET /analytics/hotspots

Current predicted hotspot clusters.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `category` | string | Filter by category |

**Response: 200 OK** — `HotspotOut[]`
```json
[
  {
    "id": "uuid",
    "latitude": 18.5204,
    "longitude": 73.8567,
    "radius_meters": 500,
    "category": "pothole",
    "issue_count": 23,
    "confidence": 0.87,
    "generated_at": "2024-01-15T06:00:00Z"
  }
]
```

---

### GET /analytics/heatmap

Issue density data for Leaflet heatmap layer.

| | |
|--|--|
| **Auth Required** | No |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `category` | string | Filter by category |
| `ward` | string | Filter by ward (partial match) |

**Response: 200 OK** — Array of weighted points (max 500)
```json
[
  {"lat": 18.5204, "lng": 73.8567, "weight": 0.85},
  {"lat": 18.5210, "lng": 73.8571, "weight": 0.45}
]
```

---

## Admin

All admin routes require `is_official=True` or `is_admin=True`. Specific endpoints note if `is_admin` is required exclusively.

### GET /admin/queue

Paginated issue management queue.

| | |
|--|--|
| **Auth Required** | Yes (official or admin) |

**Query Parameters:** Same as `GET /issues` — `page`, `per_page`, `status`, `category`, `severity`, `ward`, `is_emergency`

**Response: 200 OK** — PaginatedIssues (emergency issues always first)

---

### PATCH /admin/issues/bulk

Bulk status update for multiple issues.

| | |
|--|--|
| **Auth Required** | Yes (official or admin) |

**Request Body:**
```json
{
  "issue_ids": ["uuid1", "uuid2", "uuid3"],
  "status": "assigned",
  "note": "Batch assigned to Road Works Team 3"
}
```

**Response: 200 OK**
```json
{
  "updated": ["uuid1", "uuid2"],
  "skipped": [],
  "errors": [{"id": "uuid3", "error": "Cannot transition from 'resolved' to 'assigned'"}]
}
```

---

### GET /admin/users

User list with optional search. **Admin only.**

| | |
|--|--|
| **Auth Required** | Yes (admin only) |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Partial match on email, username, display_name |
| `page` | int | Default 1 |
| `per_page` | int | 1–100, default 25 |

**Response: 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "email": "priya@example.com",
      "username": "priya_s",
      "display_name": "Priya S.",
      "is_admin": false,
      "is_official": false,
      "is_banned": false,
      "department": null,
      "points": 1450,
      "level": 5,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 256,
  "page": 1,
  "per_page": 25
}
```

---

### PATCH /admin/users/{user_id}/moderate

Ban/unban user, set official status, assign department. **Admin only.**

| | |
|--|--|
| **Auth Required** | Yes (admin only) |
| **Path Param** | `user_id` — UUID |

**Request Body (all optional):**
```json
{
  "is_banned": true,
  "is_official": false,
  "department": "Roads & Infrastructure"
}
```

**Response: 200 OK**
```json
{"status": "updated", "user_id": "uuid"}
```

**Errors:** `404 NOT_FOUND`

---

### GET /admin/flags

Pending moderation flags queue. **Admin only.**

| | |
|--|--|
| **Auth Required** | Yes (admin only) |

**Query Parameters:** `page`, `per_page`

**Response: 200 OK** — Paginated flag objects sorted by flag count

---

### PATCH /admin/flags/{flag_id}

Review a moderation flag. **Admin only.**

| | |
|--|--|
| **Auth Required** | Yes (admin only) |
| **Path Param** | `flag_id` — UUID |

**Request Body:**
```json
{
  "status": "dismissed"
}
```

**Valid values:** `"dismissed"` (un-hide issue), `"reviewed"` (confirm hide)

**Response: 200 OK**
```json
{"status": "flag_reviewed", "flag_id": "uuid"}
```

---

### GET /admin/export

Export issues as CSV or JSON.

| | |
|--|--|
| **Auth Required** | Yes (official or admin) |

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `format` | string | `csv` | `csv` or `json` |
| `from_date` | string | — | ISO date (e.g. `2024-01-01`) |
| `to_date` | string | — | ISO date |
| `ward` | string | — | Partial ward name |
| `status` | string | — | Filter by status |

**Response: 200 OK** — File download (`Content-Disposition: attachment`)
- CSV: `lumen_issues.csv`
- JSON: `lumen_issues.json`

**Capped at 5,000 rows.**

---

## Media

### POST /media/upload

Standalone media upload (pre-upload before issue creation).

| | |
|--|--|
| **Auth Required** | Optional |
| **Content-Type** | multipart/form-data |

**Request:** `file` (required) + optional `issue_id` query param

**Accepted types:** JPEG, PNG, WebP images; MP4, MOV, WebM video; MP3, WAV, OGG audio

**Response: 201 Created** — IssueMediaOut
```json
{
  "id": "uuid",
  "issue_id": "00000000-0000-0000-0000-000000000000",
  "media_type": "photo",
  "file_path": "issues/uuid/image.jpg",
  "thumbnail_path": "issues/uuid/thumb_image.jpg",
  "file_size": 245760,
  "original_filename": "pothole.jpg",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Errors:** `422 VALIDATION_ERROR` (unsupported type, size exceeded)

---

### GET /media/{media_id}

Get media metadata.

| | |
|--|--|
| **Auth Required** | No |
| **Path Param** | `media_id` — UUID |

**Response: 200 OK** — IssueMediaOut

**Errors:** `404 NOT_FOUND`

---

### DELETE /media/{media_id}

Delete media record and file from disk.

| | |
|--|--|
| **Auth Required** | Yes |
| **Path Param** | `media_id` — UUID |

**Response: 204 No Content**

**Errors:** `403 FORBIDDEN` (not reporter or admin), `404 NOT_FOUND`

---

## Offline Sync

### POST /offline/sync

Batch-sync queued offline drafts.

| | |
|--|--|
| **Auth Required** | Optional |

**Request Body:**
```json
{
  "drafts": [
    {
      "device_idempotency_key": "3f7a-unique-uuid",
      "created_locally_at": "2024-01-14T22:15:00Z",
      "title": "Burst water pipe on Station Road",
      "description": "Large water pipe burst flooding the road",
      "latitude": 18.5204,
      "longitude": 73.8567,
      "address": "Station Road, Pune",
      "ward": "Ward 7",
      "severity": "high",
      "is_anonymous": false,
      "is_emergency": true,
      "category_id": null
    }
  ]
}
```

**Max 50 drafts per request.**

**Response: 200 OK**
```json
{
  "synced": [{"key": "3f7a-...", "issue_id": "uuid"}],
  "skipped": [{"key": "8b2c-...", "issue_id": "existing-uuid"}],
  "failed": [{"key": "9d1e-...", "error": "title: String too short"}]
}
```

---

## Users (Alias Routes)

These routes are mounted at `/users` as well as `/auth`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/users/me/settings` | Alias for `GET /auth/me/settings` |
| `PATCH` | `/users/me/settings` | Alias for `PATCH /auth/me/settings` |

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Liveness check — returns `{"status": "healthy"}` |
| `GET` | `/health/ready` | No | Readiness check — verifies DB connectivity |

---

## WebSocket Events (Socket.IO)

Lumen uses Socket.IO for real-time updates. Connect to the WebSocket endpoint at the same host/port as the HTTP API.

**Connection:** `io('wss://api.lumen.example.com', {transports: ['websocket']})`

### Events Emitted by Server

| Event | Room | Payload |
|-------|------|---------|
| `new_issue` | broadcast | `{id, latitude, longitude, title, severity, is_emergency, category, status}` |
| `emergency_alert` | broadcast | Same as new_issue — sent additionally for emergency issues |
| `status_update` | `issue_{id}` | `{issue_id, new_status, history_entry: {from_status, to_status, note, changed_at}}` |
| `ai_result` | `issue_{id}` | `{issue_id, ai_category, ai_severity, ai_confidence, ai_explanation, ai_summary}` |
| `comment_added` | `issue_{id}` | `{id, issue_id, content, is_official, user_id, display_name, created_at}` |
| `verification_update` | `issue_{id}` | `{issue_id, verification_count, verification_data}` |
| `issue_reopened` | `issue_{id}` | `{issue_id, dispute_count}` |
| `resolution_feedback` | `issue_{id}` | `{is_resolved, comment}` |
| `admin_action` | broadcast | `{action, target_id, actor_id}` |

### Joining a Room (Client)

```javascript
// Join issue-specific room to receive updates for that issue
socket.emit('join_issue', { issue_id: 'uuid' });

// Leave issue room
socket.emit('leave_issue', { issue_id: 'uuid' });
```

---

## Error Response Format

All errors return structured JSON:

```json
{
  "error_code": "NOT_FOUND",
  "message": "Issue with id 'uuid' not found",
  "details": {}
}
```

### Common Error Codes

| HTTP Status | Error Code | Description |
|-------------|-----------|-------------|
| 400 | `SPAM_DETECTED` | Submission detected as spam |
| 401 | `UNAUTHORIZED` | Missing or invalid JWT |
| 401 | `ACCOUNT_BANNED` | User account is banned |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `CONFLICT` | Duplicate resource (vote, flag, verification) |
| 422 | `VALIDATION_ERROR` | Request body failed validation |
| 422 | `INVALID_TRANSITION` | Invalid issue status transition |
| 422 | `PROXIMITY_REQUIRED` | Hard verification too far from issue |
| 500 | `INTERNAL_ERROR` | Unexpected server error |
