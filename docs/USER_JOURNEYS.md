# Lumen — User Journeys

This document describes the primary user journeys through the Lumen platform. Each journey traces the full interaction from entry point to resolution, including edge cases and system behaviour at each step.

---

## Journey 1: Citizen Reports a Pothole (Online)

**Persona:** Priya, 34, daily commuter who hit a pothole this morning.

```
1. Open Lumen PWA in browser (mobile)
   → Map loads showing nearby issues as coloured pins
   → Priya sees a green FAB (Floating Action Button): "Report Issue"

2. Tap FAB → ReportIssueModal opens (Step 1: Describe)
   → Category grid displayed (AI will confirm later)
   → Priya selects "Pothole" icon
   → Types description: "Deep pothole near Kalyani Nagar junction, causing tyre damage"

3. Step 2: Add Media
   → Priya taps "Take Photo" → camera opens
   → Photo captured, thumbnail shown in modal
   → Taps "Next"

4. Step 3: Confirm Location
   → Browser geolocation API returns current GPS position
   → Map shows pin at her location
   → Priya confirms (or drags pin to correct position)
   → Duplicate check runs: GET /issues/check-duplicates
     → 0 duplicates found → proceeds
   → Priya taps "Submit"

5. POST /issues (multipart)
   ← 201 Created: IssueOut returned immediately
   → Toast: "Your report is live!"
   → Map pin appears instantly (yellow = reported)

6. (async, 5–15 seconds)
   → Celery AI task completes
   → ai_result socket event arrives
   → Issue detail shows: "AI Classification: Pothole | Severity: High | 91% confidence"

7. Priya closes modal → her issue pin is visible on the map
   → She can tap it to see status: "reported"
```

**Alternative: Duplicate Found (Step 4)**
```
→ DuplicateSuggestionPanel appears: "2 similar issues found nearby"
→ Priya sees existing issue: "Pothole at Kalyani Nagar junction – Reported 2 days ago"
→ She taps "Support This Issue" → POST /issues/{id}/support
→ vote_count increments → toast: "Thanks! Your support has been added."
→ Original reporter's issue moves up priority queue
```

---

## Journey 2: Citizen Reports a Burst Water Pipe (Offline)

**Persona:** Rajan, 52, reports on a 2G connection that drops frequently.

```
1. Open Lumen PWA → map loads from service worker cache (offline shell)
   → Network request for /issues/nearby fails silently
   → Cached map tiles shown

2. Tap FAB → ReportIssueModal opens
   → Rajan types description; selects "Water Leakage"

3. Taps "Submit" → network unavailable
   → Service worker intercepts POST /issues
   → Draft stored in IndexedDB with UUID idempotency key
   → Toast: "Saved offline. Will submit when connected."
   → OfflineSyncBanner appears at top of screen

4. Rajan closes app. Later, network returns.
   → Background Sync API fires
   → Service worker calls POST /offline/sync with draft batch
   → Server creates issue; marks draft synced=True
   → OfflineSyncBanner disappears
   → Toast: "Your offline report was submitted!"

5. Rajan reopens app → his issue pin visible on map
```

---

## Journey 3: Community Member Verifies an Issue

**Persona:** Aisha, 28, passes the pothole daily on her scooter.

```
1. Aisha opens Lumen → taps pothole pin on map
2. Issue detail panel opens: "Large pothole — Reported | 1 verification"
3. She taps "I can confirm this" → VerifyModal opens

4. Option A: Hard Verify (on-site)
   → Aisha is physically at the pothole
   → Browser requests GPS → she allows
   → Proximity check: her GPS is 45m from issue → within 100m ✓
   → POST /issues/{id}/verify {verification_type: "hard", latitude, longitude}
   ← 201: verification recorded, trust_weight: 1.0, points: 25
   → Toast: "Hard verification recorded. +25 points"

5. Option B: Soft Verify (remote knowledge)
   → Aisha confirms from memory (commutes past daily)
   → POST /issues/{id}/verify {verification_type: "soft"}
   ← 201: trust_weight: 0.5, points: 10

6. If weighted_score ≥ 2.0:
   → Issue status auto-upgrades: reported → verified
   → status_update socket event fires
   → Map pin colour changes: yellow → orange (verified)
   → Original reporter gets notification: "Your issue was verified!"
```

---

## Journey 4: Ward Official Resolves an Issue

**Persona:** Sanjay, Ward 12 Public Works Officer.

```
1. Sanjay logs in with is_official=True account
   → Lands on Admin Queue (GET /admin/queue)
   → Emergency issues shown first (red badge)
   → Sanjay filters by: ward=12, status=verified, severity=high

2. Opens pothole issue
   → Reads description, views photo, sees 3 hard verifications
   → Taps "Assign" → AssignModal opens
   → Assigns to repair crew, sets due date: 3 days
   → POST /issues/{id}/assign {assigned_to, department, due_date}
   ← status changes to "assigned"
   → status_update socket event: citizen's app updates in real time

3. Crew completes repair 2 days later
   → Sanjay opens issue → taps "Mark In Progress"
   → PATCH /issues/{id}/status {status: "in_progress"}

4. Repair confirmed complete
   → Sanjay taps "Resolve" → adds note: "Pothole filled and compacted"
   → PATCH /issues/{id}/status {status: "resolved"}
   → resolved_at timestamp recorded
   → Citizen Priya receives notification: "Your issue has been resolved!"

5. Citizen resolution feedback (7 days open)
   → Priya opens app → sees "Tell us if this was fixed"
   → POST /issues/{id}/resolution-feedback {is_resolved: true}
   → Priya earns +25 "resolve_confirmed" points
   → Issue status → closed
```

**Dispute flow:**
```
   → If Priya selects "Not fixed" and 2 others also dispute:
   → dispute_count = 3 ≥ threshold
   → Issue auto-reopens: status → disputed
   → emit_issue_reopened socket event
   → Issue re-enters Sanjay's queue
```

---

## Journey 5: Admin Manages a Moderation Flag

**Persona:** Lumen Admin.

```
1. Citizen flags an issue: "Spam / Duplicate"
   → POST /issues/{id}/flag {reason: "spam"}
   → Flag saved; moderation.process_flag() checks flag count

2. If flag_count ≥ 5 (threshold):
   → Issue auto-hidden (is_hidden=True)
   → Admin receives dashboard alert

3. Admin opens flag queue: GET /admin/flags
   → Sees issue with 5 flags, reason breakdown
   → Reviews issue content + photos

4. Admin options:
   A. Dismiss flags → PATCH /admin/flags/{id} {status: "dismissed"}
      → Issue un-hidden
   B. Confirm hidden → PATCH /admin/flags/{id} {status: "reviewed"}
      → Issue stays hidden; spam_score updated
   C. Ban user → PATCH /admin/users/{id}/moderate {is_banned: true}
      → User blocked from further submissions

5. All admin actions logged in IssueAuditLog with actor_id
```

---

## Journey 6: New User Registers and Earns Their First Badge

**Persona:** Meera, first-time user.

```
1. Opens Lumen → taps "Sign Up"
   → POST /auth/register {email, password, username, display_name}
   ← TokenResponse: JWT + UserMe profile
   → Stored in localStorage; subsequent requests include Authorization header

2. Meera reports her first issue
   → POST /issues → 201
   → award_points("report_issue") → +10 points
   → _check_badges(): "first_report" condition met → badge awarded
   → Badge notification: "🏅 First Report! You reported your first issue."

3. Meera opens Profile page: GET /gamification/me
   → Points: 10 | Level: 1 | Badges: 1 | Streak: 1 day

4. Meera verifies another issue: +5 points (soft) or +25 (hard)
5. After 7 consecutive daily actions → "streak_7" badge unlocked
6. After 100 points → "century" badge unlocked
```

---

## Journey 7: Guest User (No Registration)

```
1. Opens Lumen → taps "Continue as Guest"
   → POST /auth/guest
   ← {guest_session_id, access_token}
   → JWT stored for this session

2. Guest can:
   → Report issues (attributed to session)
   → Vote (POST /issues/{id}/support)
   → View map, filter, search

3. Guest cannot:
   → Accumulate points across sessions
   → View leaderboard or profile
   → Access admin features

4. If guest closes browser → session lost
   → Offline drafts tied to guest_session_id may be recovered if session token persists
```
