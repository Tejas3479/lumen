# Lumen — Admin Workflow

## Overview

Lumen provides a privileged admin interface for municipal officials and platform administrators to manage issue queues, moderate content, manage users, and export data. Access is role-gated at the API level.

---

## Role Definitions

| Role | Flag | Capabilities |
|------|------|-------------|
| **Citizen** | `is_official=False, is_admin=False` | Report, vote, verify, comment |
| **Official** | `is_official=True` | All citizen actions + admin queue, status updates, assignments, export |
| **Admin** | `is_admin=True` | All official actions + user management, flag review, user moderation, ban |

**Note:** `is_admin=True` implies `is_official=True` by the `get_official_or_admin` dependency. An admin has all official capabilities plus destructive/moderation powers.

**Official vs. Admin distinction:**
- Officials are ward-level civil servants. They manage issues within their domain.
- Admins are platform operators. They manage users, moderate content, and have full access across all wards.
- An official cannot ban users or review moderation flags. An admin can do everything.

---

## Admin Queue

### Endpoint

```
GET /admin/queue
Auth: is_official OR is_admin
```

### Sorting Logic

Emergency issues are **always shown first** regardless of other sort parameters. Within emergency and non-emergency groups, issues are sorted by:
1. Severity (critical → high → medium → low)
2. Created at (oldest first, to prevent starvation)

This means an admin opening the queue always sees the highest-risk, longest-waiting issues at the top.

### Filter Combinations

All filters are optional and fully combinable:

| Filter | Type | Example |
|--------|------|---------|
| `status` | string | `verified`, `in_progress`, `assigned` |
| `category` | string | `pothole`, `water_leakage` |
| `severity` | string | `critical`, `high` |
| `ward` | string | `Ward 12` (partial match) |
| `is_emergency` | boolean | `true` |
| `page` / `per_page` | int | `page=1&per_page=25` |

---

## Status Transition State Machine

Issue status follows a strict directed acyclic graph. Invalid transitions are rejected with HTTP 422.

```
                    ┌─────────────────────────────┐
                    │                             │
         ┌──────────▼──────────┐                 │
         │      REPORTED       │                 │
         └──────────┬──────────┘                 │
                    │ community weighted score ≥ 2.0  (auto)
                    │ OR official manually verifies
                    ▼
         ┌─────────────────────┐
         │      VERIFIED       │
         └──────────┬──────────┘
                    │ official assigns crew
                    ▼
         ┌─────────────────────┐
         │      ASSIGNED       │
         └──────────┬──────────┘
                    │ work begins
                    ▼
         ┌─────────────────────┐
         │    IN_PROGRESS      │
         └──────────┬──────────┘
                    │ official marks resolved
                    ▼
         ┌─────────────────────┐   3+ citizen disputes
         │      RESOLVED       │──────────────────────►  DISPUTED
         └──────────┬──────────┘                            │
                    │ no disputes in 7 days                 │ official re-resolves
                    ▼                                       ▼
         ┌─────────────────────┐              ┌─────────────────────┐
         │       CLOSED        │◄─────────────│      RESOLVED       │
         └─────────────────────┘              └─────────────────────┘
```

**Allowed transitions (enforced server-side):**

| From | To | Who |
|------|----|-----|
| `reported` | `verified` | Auto (community) or Official |
| `reported` | `assigned` | Official (skips verification step) |
| `verified` | `assigned` | Official |
| `assigned` | `in_progress` | Official |
| `in_progress` | `resolved` | Official |
| `resolved` | `disputed` | Auto (3+ citizen disputes) |
| `resolved` | `closed` | Official or Auto (7-day timer, future) |
| `disputed` | `in_progress` | Official (re-investigating) |
| `disputed` | `resolved` | Official (re-resolving) |
| `*` | `closed` | Admin (force close) |

Any transition not in this table returns:
```json
{"error_code": "INVALID_TRANSITION", "message": "Cannot transition from 'reported' to 'resolved'"}
```

---

## Bulk Update Flow

Admins can update multiple issues simultaneously:

```
PATCH /admin/issues/bulk
Auth: is_official OR is_admin
Body: {
  "issue_ids": ["uuid1", "uuid2", "uuid3"],
  "status": "assigned",
  "note": "Batch assigned to Road Works Team 3"
}
```

**Server processing:**
1. For each `issue_id`, call `change_issue_status()` — validates the transition individually.
2. Emit `status_update` Socket.IO event for each successfully updated issue.
3. Failures are collected but do not abort the batch.

**Response:**
```json
{
  "updated": ["uuid1", "uuid2"],
  "skipped": [],
  "errors": [{"id": "uuid3", "error": "Cannot transition from 'resolved' to 'assigned'"}]
}
```

**Logged:** Admin ID, target status, count of updated/errored — logged to structured log and `IssueAuditLog`.

---

## Moderation: Flag Threshold → Auto-Hide

### Flag Flow

1. A citizen flags an issue: `POST /issues/{id}/flag {reason, detail}`.
2. Flag is saved as `Flag` record with `status="pending"`.
3. `moderation.process_flag()` counts active flags on the issue.
4. If `flag_count ≥ settings.flag_threshold` (default: **5**):
   - `issue.is_hidden = True` — issue no longer appears in public feeds.
   - `issue.spam_score` incremented.
   - All connected clients receive a silent map update (pin disappears).

### Flag Reasons

| Reason | Description |
|--------|-------------|
| `spam` | Fabricated or junk content |
| `duplicate` | Exact duplicate of existing issue |
| `inappropriate` | Offensive or irrelevant content |
| `resolved` | Issue already fixed (no official action taken) |
| `wrong_location` | GPS location is clearly wrong |

### Admin Flag Review

`GET /admin/flags` returns all pending flags sorted by flag count (most-flagged first).

`PATCH /admin/flags/{flag_id}`:
- `{status: "dismissed"}` — removes the flag, un-hides the issue if flag_count drops below threshold.
- `{status: "reviewed"}` — confirms the hide action; spam_score permanently updated.

---

## Export: CSV/JSON

```
GET /admin/export?format=csv&from_date=2024-01-01&to_date=2024-12-31&ward=Ward+12&status=resolved
Auth: is_official OR is_admin
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `format` | `csv` \| `json` | Output format |
| `from_date` | ISO date string | Filter: created_at >= from_date |
| `to_date` | ISO date string | Filter: created_at <= to_date |
| `ward` | string | Partial match on ward name |
| `status` | string | Filter by status |

**Output fields (both formats):**

| Field | Description |
|-------|-------------|
| ID | Issue UUID |
| Title | Issue title |
| Category | Category name |
| Severity | low/medium/high/critical |
| Status | Current status |
| Ward | Ward name |
| Address | Human-readable address |
| Latitude, Longitude | GPS coordinates |
| Votes | Vote count |
| Verifications | Verification count |
| Emergency | Yes/No |
| Created At | ISO timestamp |
| Resolved At | ISO timestamp or blank |

**Limits:** Capped at **5,000 rows** per export request to prevent memory exhaustion. For larger exports, officials should use date range filters to paginate across multiple exports.

---

## User Management

### List Users

```
GET /admin/users?search=priya&page=1&per_page=25
Auth: is_admin (NOT is_official — officials cannot see the user list)
```

Search matches against `email`, `username`, and `display_name` (case-insensitive partial match).

### Moderate User

```
PATCH /admin/users/{user_id}/moderate
Auth: is_admin
Body: {
  "is_banned": true,           // ban/unban
  "is_official": true,         // promote to official
  "department": "Roads & Infra" // assign department
}
```

**Effects of banning:**
- `user.is_banned = True`
- Subsequent login attempt returns `401 UNAUTHORIZED: Account is banned`
- User's issues remain visible (historical record preserved)
- User's future submissions are blocked at `POST /issues` before creation

**All moderation actions** emit `admin_action` Socket.IO event (visible to other admins) and are logged in `IssueAuditLog`.

---

## Admin Audit Trail

Every admin action is recorded:

```sql
-- issue_audit_log table
id           UUID
issue_id     UUID    -- affected issue (if applicable)
actor_id     UUID    -- admin who performed the action
action       VARCHAR -- e.g. "status_change", "bulk_update", "user_moderated"
before_state JSONB
after_state  JSONB
created_at   TIMESTAMPTZ
```

This log is immutable (no update/delete on audit records) and provides a full history of every administrative action for accountability and dispute resolution.
