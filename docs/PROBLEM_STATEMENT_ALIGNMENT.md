# Lumen — Problem Statement & Alignment

## The Problem

Urban India faces a persistent breakdown in the feedback loop between citizens and municipal bodies. Citizens encounter broken infrastructure daily — potholes causing vehicle damage, burst water pipes flooding roads, non-functional streetlights creating safety hazards, overflowing garbage bins spreading disease — but lack an efficient, trusted mechanism to report these issues and track their resolution.

### Current Situation

| Gap | Impact |
|-----|--------|
| No unified digital reporting channel | Citizens call helplines, post on social media, or give up |
| Reports lost in administrative handoffs | Issues remain unresolved for months |
| No visibility on issue status | Citizens cannot tell if their report was received or acted upon |
| Officials have no prioritisation tool | All issues look equal; emergencies are not triaged first |
| No accountability data | Municipal bodies cannot demonstrate performance or identify patterns |
| No community signal | Duplicate reports waste official time; community consensus is invisible |

---

## How Lumen Solves It

### 1. Frictionless Reporting
- Citizens report in under 60 seconds: open app, take photo, confirm location.
- Works offline: reports queued in IndexedDB, synced automatically when connectivity returns.
- Anonymous reporting available for safety-sensitive situations.
- Guest session (no account required) for one-off reports.

### 2. AI-Assisted Categorisation and Triage
- GPT-4V analyses the submitted photo and description, assigns a category (pothole, water leakage, streetlight, garbage, drainage, other), severity (low → critical), and confidence score.
- Emergency issues (critical severity + `is_emergency=True`) trigger an immediate `emergency_alert` socket broadcast to all connected officials.
- Pre-submit duplicate detection prevents multiple citizens reporting the same pothole independently — they are offered "Support this issue" instead.

### 3. Community Verification
- A single report may be noise; verified reports are signal.
- Hard verification (GPS proximity ≤ 100m) and soft verification (personal knowledge) create a trust-weighted score.
- Two hard verifications — or the equivalent weighted score of 2.0 — automatically escalates an issue from `reported` → `verified`.
- This filters out spam without requiring official review of every submission.

### 4. Official Workflow and Accountability
- Officials see a prioritised queue (emergencies first, then by severity and ward).
- Status machine: `reported → verified → assigned → in_progress → resolved → closed`.
- Citizens can dispute resolutions; 3+ disputes automatically reopen the issue to `disputed`.
- Every status change is recorded in `status_history` with timestamp and actor.

### 5. Transparency and Trust
- Every issue's status history is public and visible in the issue detail view.
- Real-time socket events push status changes to the citizen who reported it.
- Resolution feedback from citizens (confirm vs. dispute) closes the accountability loop.
- Dashboard statistics (resolution rate, average days, top wards) are public.

### 6. Gamification for Sustained Engagement
- Points, levels, badges, and streaks incentivise citizens to report, verify, and follow through.
- Leaderboard shows pseudonymous rankings — privacy preserved while fostering community spirit.
- Anti-gaming: points only for actions that pass spam and verification checks.

---

## Alignment with Urban Governance Goals

| Civic Goal | Lumen Feature |
|------------|---------------|
| Reduce MTTR for infrastructure issues | Status tracking + official queue + assignments |
| Citizen-centric services | Real-time updates, resolution feedback, anonymous reporting |
| Data-driven decisions | Analytics dashboard, heatmap, predictive hotspots |
| Accountability of public works | Immutable audit log, public status history |
| Inclusivity | Offline mode, voice input, high-contrast mode, WCAG 2.1 AA |
| Reduce duplicate service requests | Pre-submit duplicate detection + "Support existing issue" |

---

## Target Users

| User Type | Primary Need | Key Features |
|-----------|-------------|--------------|
| Citizen (general) | Report a problem quickly | 3-step form, offline support, status updates |
| Citizen (accessibility) | Report without barriers | Voice input, screen reader support, high contrast |
| Guest | One-off report without registration | Guest session, no account needed |
| Ward Official | Manage and resolve assigned issues | Admin queue, status updates, bulk actions |
| City Admin | Oversight, analytics, moderation | Full admin panel, export, user moderation |

---

## Non-Goals (Out of Scope for v1)

- Financial payments or procurement workflows.
- Integration with existing municipal ERP systems (future: REST adapter).
- Native mobile apps (iOS/Android) — PWA covers the offline/mobile use case.
- Legal enforcement — Lumen creates civic pressure, not legal mandates.
- Private property issues — public infrastructure only.
