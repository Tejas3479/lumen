# Lumen — Gamification System

## Overview

Lumen's gamification system incentivises citizens to report issues, verify existing reports, and sustain engagement over time. Points, levels, badges, and streaks create a feedback loop that transforms civic responsibility into a rewarding community activity.

---

## Points Table

All point values are defined in `app/services/gamification.py` (`POINT_VALUES` dict):

| Action | Points | Notes |
|--------|--------|-------|
| `report_issue` | **10** | Awarded on successful issue creation |
| `verify_issue` (soft) | **10** | Soft verification (no GPS required) |
| `verify_issue` (hard) | **25** | Hard verification (GPS within 100m) |
| `first_responder` | **+15** | Bonus on top of verify points — first verifier on a new issue |
| `emergency_report` | **20** | Reporting an issue with `is_emergency=True` |
| `resolve_confirmed` | **25** | Reporter confirms their issue was actually fixed |
| `daily_streak` | **3** | Per day of continuous activity (awarded on each qualifying action) |
| `flag_accepted` | **5** | Flag submitted by user results in admin action taken |
| `comment_pinned` | **10** | Official or admin pins user's comment as notable |

### Negative Points (Anti-Spam)

| Action | Points |
|--------|--------|
| `spam_submission` | **-20** | Issue detected as spam and rejected |
| `false_flag` | **-5** | Flag dismissed by admin as malicious |

Negative points are deducted from `user.points` but cannot reduce total below 0 (minimum points floor: 0).

---

## Level Thresholds

Levels use a progressive threshold formula: Level N requires `N × (N-1) / 2 × 100` total points to reach.

| Level | Cumulative Points Required | Label |
|-------|--------------------------|-------|
| 1 | 0 | Newcomer |
| 2 | 100 | Reporter |
| 3 | 300 | Contributor |
| 4 | 700 | Advocate |
| 5 | 1,500 | Champion |
| 6 | 2,100 | Expert |
| 7 | 2,800 | Guardian |
| … | … | … |

**Level calculation function:**

```python
def level_for_points(points: int) -> int:
    level = 1
    threshold = 0
    while True:
        threshold += level * 100  # 100, 200, 300, 400, ...
        if points < threshold:
            break
        level += 1
    return level
```

The UI shows progress to the next level as a progress bar:
```
Level 3 ──────────────────────────░░░░ Level 4
         300 pts                        700 pts
              (450 pts / 400 pts to go)
```

---

## Badge Conditions

All badge conditions are evaluated after every point award in `_check_badges()`.

| Badge Name | Display Name | Condition | Icon |
|------------|-------------|-----------|------|
| `first_report` | First Report | `issues_reported >= 1` | 📍 |
| `reporter_5` | Active Reporter | `issues_reported >= 5` | 📋 |
| `reporter_25` | Prolific Reporter | `issues_reported >= 25` | 🏆 |
| `verifier_10` | Community Verifier | `verifications >= 10` | ✅ |
| `streak_7` | Week Warrior | `streak_days >= 7` | 🔥 |
| `streak_30` | Month Guardian | `streak_days >= 30` | 🔥🔥 |
| `first_responder` | First Responder | `first_responder_count >= 1` | ⚡ |
| `resolver` | Problem Solver | `confirmed_resolved >= 5` | 🔧 |
| `century` | Century Club | `points >= 100` | 💯 |
| `champion` | Champion | `points >= 1000` | 🥇 |

**Badge award rules:**
- Each badge is awarded exactly once per user (enforced by `UserBadge` unique constraint on `user_id + badge_id`).
- Only one badge is returned per `award_points()` call (the first newly-unlocked badge). Multiple badges may be unlocked in separate calls.
- Frontend shows a badge notification card when `badge_unlocked` is non-null in the gamification response.

---

## Streak Calculation Logic

A streak represents consecutive days of activity. The streak counter is updated on every `award_points()` call:

```python
today = date.today()

if user.last_active_date != today:
    if user.last_active_date is None:
        # First ever activity
        user.streak_days = 1
    elif (today - user.last_active_date).days == 1:
        # Consecutive day — extend streak
        user.streak_days += 1
    else:
        # Gap of ≥ 2 days — streak broken, restart
        user.streak_days = 1
    
    user.last_active_date = today
```

**Streak rules:**
- Streak increments once per day maximum, regardless of how many actions the user takes.
- Missing a day breaks the streak (reset to 1 on the next action).
- `daily_streak` points (3 pts) are awarded for each day that extends the streak, irrespective of which action triggered the update.
- Guest users do not accumulate streaks (their `last_active_date` is not tracked across sessions).

---

## Anti-Gaming Rules

### 1. Points Only for Verified Actions

Points are **not** awarded until the underlying action passes all validation:
- `report_issue`: only after spam check passes and issue is successfully created.
- `verify_issue`: only after proximity check (hard) or duplicate guard passes.
- `resolve_confirmed`: only after the issue was in `resolved` status when feedback was submitted.

### 2. No Self-Verification

As documented in `VERIFICATION_SYSTEM.md`, a user cannot verify their own issue. Attempting to do so raises `ForbiddenError` and awards 0 points.

### 3. Spam Penalty

The spam detector (`app/services/spam_detector.py`) applies a `-20` point deduction when a submission is detected as spam. This disincentivises rapid-fire junk reports.

### 4. Guest Users Excluded

Users where `user.is_guest = True` receive 0 points for all actions:
```python
if not user or user.is_guest:
    return {"points_awarded": 0, ...}
```

This prevents the creation of throwaway accounts for point farming.

### 5. Negative Floor

`user.points` cannot go below 0 (clamped at DB layer). Users who receive spam penalties retain a floor of 0 rather than going negative.

---

## Leaderboard

### Periods

| Period | Points Considered | Refresh |
|--------|------------------|---------|
| `all_time` | Total lifetime `user.points` | Real-time |
| `monthly` | Points earned in last 30 days | Real-time (via `leaderboard_points` log) |
| `weekly` | Points earned in last 7 days | Real-time (via `leaderboard_points` log) |

### Leaderboard Entry Fields

```json
{
  "rank": 1,
  "user_id": "uuid",
  "display_name": "Priya S.",
  "pseudonym": "CivicHero_42",
  "points": 1450,
  "level": 5,
  "badge_count": 7,
  "issues_resolved_count": 12,
  "streak_days": 23
}
```

### Pseudonym Privacy on Leaderboard

The `display_name` is shown publicly on the leaderboard by default. If a user has set `is_anonymous_default = True` in their profile:
- The `pseudonym` field is shown instead of `display_name`.
- `display_name` is hidden.
- The `user_id` remains present for frontend linking to the public profile.

Pseudonyms are set by the user via `PATCH /auth/me/settings {pseudonym: "CivicHero_42"}`. They are unique across all users.

Guest and banned users are **excluded** from all leaderboards.

---

## Gamification API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/gamification/leaderboard` | Optional | Paginated leaderboard (all_time/monthly/weekly) |
| `GET` | `/gamification/me` | Required | Current user's full stats |
| `GET` | `/gamification/users/{id}` | Optional | Another user's public profile |
| `GET` | `/gamification/badges` | Optional | Full badge catalogue |
