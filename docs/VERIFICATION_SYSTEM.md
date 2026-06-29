# Lumen — Verification System

## Overview

The Lumen verification system allows community members to confirm that a reported issue genuinely exists. This transforms a single unverified report — which could be spam, a mistake, or a duplicate — into a community-validated signal that officials should prioritise.

---

## Hard vs. Soft Verification

### Definitions

| Type | Definition | Requirement |
|------|-----------|-------------|
| **Hard** | The verifier is physically present at or near the issue location. | GPS latitude and longitude must be submitted with the request. |
| **Soft** | The verifier confirms the issue from personal knowledge (regular commute, memory, second-hand information). | No location data required. |

### Rationale for the Distinction

Hard verification is a stronger signal because it requires the verifier to physically be at the location — which is significantly harder to fake than clicking a button remotely. By assigning different trust weights to each type, the system incentivises genuine on-site confirmation while still allowing valuable soft confirmations from people who know the area well but cannot physically visit.

---

## Trust Weight Scoring

| Verification Type | Trust Weight |
|-------------------|-------------|
| Hard | **1.0** |
| Soft | **0.5** |

The **weighted verification score** for an issue is the sum of all trust weights across all verifications on that issue:

```
weighted_score = Σ trust_weight(v) for all v in issue.verifications
```

**Examples:**
- 2 hard verifications → 2 × 1.0 = **2.0**
- 4 soft verifications → 4 × 0.5 = **2.0**
- 1 hard + 2 soft verifications → 1.0 + 2 × 0.5 = **2.0**

---

## Auto-Upgrade Threshold

When `weighted_score ≥ 2.0` **AND** the current issue status is `reported`:

- Issue status automatically transitions to **`verified`**
- A `StatusHistory` record is created: `from_status="reported"`, `to_status="verified"`, `is_official=False`, `note="Auto-verified by community"`
- A `status_update` Socket.IO event is emitted so all connected clients update the map pin colour in real time (yellow → orange)
- The original reporter receives a notification: "Your issue has been verified by the community!"

The threshold constant (`WEIGHTED_SCORE_FOR_VERIFIED = 2.0`) is defined in `app/services/verification_service.py` and can be adjusted without code changes by updating the constant and deploying.

---

## Proximity Check (Hard Verification)

For hard verifications, the server validates that the verifier's submitted GPS coordinates are within the configured radius of the issue's recorded location.

**Algorithm:** Haversine formula (great-circle distance)

```python
def is_within_radius(
    point_lat: float, point_lng: float,
    center_lat: float, center_lng: float,
    radius_meters: float
) -> bool:
    # Haversine implementation in app/services/geo_utils.py
```

**Default radius:** `100 metres` (configured as `settings.hard_verification_radius_meters`)

If the distance exceeds 100m, the API returns:
```json
{
  "error_code": "PROXIMITY_REQUIRED",
  "message": "You must be within 100m of the issue to perform a hard verification. Try soft verification instead."
}
```

The 100m radius was chosen as a balance between:
- Being strict enough to require genuine presence (eliminates the next block over)
- Being lenient enough to account for GPS jitter (typical mobile GPS accuracy: ±5–30m in urban canyons)

---

## Anti-Gaming Rules

### 1. No Self-Verification
A user cannot verify their own issue.

```python
if issue.reporter_id == user_id:
    raise ForbiddenError("You cannot verify your own issue")
```

This prevents a single user from reporting a fake issue and immediately verifying it.

### 2. One Verification Per User Per Issue
```python
existing = await db.execute(
    select(Verification).where(
        Verification.issue_id == issue_id,
        Verification.user_id == user_id,
    )
)
if existing.scalar_one_or_none():
    raise ConflictError("You have already verified this issue")
```

### 3. Terminal Status Guard
Issues in `resolved`, `closed`, or `disputed` states cannot receive new verifications:

```python
if issue.status in ("resolved", "closed", "disputed"):
    raise ValidationError("Cannot verify a resolved, closed, or disputed issue")
```

### 4. Guest Verifiers
Guest users (no registered account) can verify issues but receive a lower effective trust weight. Guest soft verifications have trust weight 0.25 (half of registered-user soft). This is configurable.

---

## Points Awarded

| Action | Points |
|--------|--------|
| Hard verification | **25 pts** |
| Soft verification | **10 pts** |
| First verifier on a new issue (first responder bonus) | **+15 pts** additional |

Points are awarded via the `award_points()` service function and recorded in `leaderboard_points`.

---

## Dispute and Reopen Flow

After an issue is marked `resolved`, citizens can submit resolution feedback:

```
POST /issues/{id}/resolution-feedback
{
  "is_resolved": false,
  "comment": "The pothole is still there, just patched with dirt"
}
```

**Resolution feedback logic:**
1. `ResolutionFeedback` record created.
2. If `is_resolved=False`, dispute count for this issue is computed.
3. If `dispute_count ≥ settings.dispute_reopen_threshold` (default: **3**):
   - Issue status transitions: `resolved → disputed`
   - `StatusHistory` created: auto-reopened by community disputes
   - `emit_issue_reopened(issue_id, dispute_count)` → Socket.IO broadcast
   - Issue re-enters the admin queue

**Why 3 disputes?**
- 1 dispute may be a misunderstanding.
- 2 disputes are borderline.
- 3 disputes represent a clear community consensus that the resolution was unsatisfactory.

Citizens who dispute receive +5 points for the feedback (regardless of whether it triggers a reopen).

---

## Accessibility Accommodation: Soft Verification for Mobility-Limited Users

Users with mobility limitations who have been marked as accessibility users in their preferences are shown a clear explanation that **soft verification is equally valid** and requires no physical travel to the site:

> *"You don't need to visit the location. If you know this issue exists from your regular experience of this area, soft verification is a meaningful contribution."*

The soft verification option is presented first (rather than second) in the UI for users with `privacy_settings.mobility_limited = true`.

This ensures the verification system does not exclude users who cannot physically travel to an issue location.

---

## State Transition for Verification

```
Issue: status="reported", verification_count=0, weighted_score=0.0
   │
   ├── Hard verify by User A → weighted_score = 1.0, verification_count = 1
   │
   ├── Soft verify by User B → weighted_score = 1.5, verification_count = 2
   │
   └── Hard verify by User C → weighted_score = 2.5 ≥ 2.0
              │
              ▼
       Issue: status="verified"  ← auto-upgrade
       StatusHistory: reported → verified (auto, community)
       Socket.IO: status_update event
       Map pin: yellow → orange
```

---

## Database Schema (Relevant Fields)

```sql
-- verifications table
id                UUID PRIMARY KEY
issue_id          UUID REFERENCES issues(id)
user_id           UUID REFERENCES users(id)
verification_type VARCHAR  -- 'hard' or 'soft'
trust_weight      FLOAT    -- 1.0 or 0.5
comment           TEXT
latitude          FLOAT    -- submitted location (hard verify only)
longitude         FLOAT
distance_meters   FLOAT    -- computed Haversine distance at verify time
created_at        TIMESTAMPTZ

-- issues table (relevant columns)
verification_count  INTEGER DEFAULT 0  -- incremented on each verify
weighted_verification_score  FLOAT DEFAULT 0.0  -- sum of trust_weights
```
