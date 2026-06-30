# Lumen — Known Limitations

This document honestly catalogues the current limitations of the Lumen v1 platform — technical, UX, operational, and scope constraints — and distinguishes between intentional deferral and acknowledged technical debt.

---

## 1. AI Categorisation

### 1.1 Accuracy on Low-Quality Images
Gemini 3.5 Flash performs well on clear daytime photos. Accuracy degrades significantly on:
- Night-time or poorly lit photos
- Blurry or heavily compressed images
- Photos submitted from inside moving vehicles
- Issues without a distinctive visual signature (e.g., noise complaints, smell)

**Mitigation:** Confidence score surfaced to user. Low-confidence results (< 0.5) show "Uncertain — please verify category manually."

### 1.2 No Fine-Tuning on Indian Civic Data
The system uses base Gemini 3.5 Flash with a hand-crafted system prompt. There is no fine-tuning on labelled Indian civic issue photographs. Category accuracy may drift from urban-Western training data biases.

**Planned fix:** See `FUTURE_SCOPE.md §1` — fine-tuning pipeline using correction feedback.

### 1.3 API Cost at Scale
Gemini 3.5 Flash image analysis costs approximately $0.0003–$0.0006 per issue with image. At 10,000 issues/month, this is extremely manageable (~$6/month). At city-scale (1M issues/month), a dedicated fine-tuned model becomes economically necessary to ensure 100% localization.

### 1.4 Fallback Confidence Is 0.0
When all AI providers fail and the text-only fallback is used, `ai_confidence` is set to 0.0. This is correct but visually abrupt for users. A better UX would distinguish "text-only analysis" from "AI unavailable."

---

## 2. Verification System

### 2.1 GPS Spoofing Vulnerability
Hard verification requires the user's GPS to be within 100m of the issue. Mobile GPS can be spoofed with developer tools. The system does not perform device attestation or detect impossible travel speeds.

**Planned fix:** Server-side velocity check (two hard verifications from the same user within 1 minute at locations >1km apart should flag both for review).

### 2.2 Soft Verification Is Easily Gamed by Coordinated Groups
Soft verification requires no location. A coordinated group of 4 users could soft-verify a fabricated issue to the "verified" state (4 × 0.5 = 2.0). The spam detector mitigates this for individual spammers but not coordinated ring attacks.

**Planned fix:** Rate-limit soft verifications per IP subnet; require email verification before soft-verify privilege.

### 2.3 No Negative Verification
There is no "I don't see this issue" mechanism. An issue that has been resolved informally may still accumulate verifications from people who haven't visited recently.

---

## 3. Offline Sync

### 3.1 Background Sync API Browser Support
The Background Sync API (`navigator.serviceWorker.ready.sync.register()`) is supported in Chromium-based browsers but **not in Safari/WebKit** (as of mid-2026). On Safari, drafts sync only when the user reopens the app and is online.

**Workaround:** On `online` event, the app attempts sync immediately via `navigator.onLine` check + manual POST.

### 3.2 Offline Map Tiles Limited to Pre-Cached Area
The service worker caches map tiles for the region viewed while online. Areas never visited remain blank offline. There is no pre-fetch for the user's home ward.

### 3.3 IndexedDB Quota Limits
Mobile browsers enforce storage quotas (typically 50–500MB). Heavy users with many unsynced drafts plus cached tiles may hit the quota. No quota-exceeded handler currently shows a user-facing error.

---

## 4. Scalability

### 4.1 Single-Server Architecture
The current deployment is a single Docker Compose stack on one VPS. There is no horizontal scaling for the FastAPI app or Celery workers.

**Threshold:** The current architecture handles approximately 500 concurrent WebSocket connections and ~100 API requests/second before degradation.

**Planned fix:** See `FUTURE_SCOPE.md §3` — Kubernetes migration, read replicas, Redis Cluster.

### 4.2 Leaderboard is Computed at Query Time
The `GET /gamification/leaderboard` endpoint computes rankings from the database on each request. At >10,000 users, this query will become slow.

**Planned fix:** Materialised leaderboard view refreshed hourly via Celery task.

### 4.3 Heatmap Capped at 500 Points
`GET /analytics/heatmap` returns at most 500 data points for rendering performance. At city scale, clustering should be performed server-side before returning representative cluster centroids.

---

## 5. Security

### 5.1 JWT Has No Server-Side Revocation
Logout is stateless — the server does not maintain a token blacklist. A stolen JWT is valid until expiry (default: 30 days). This is intentional for v1 simplicity.

**Planned fix:** Redis-based token blacklist checked on each request; shorter access token TTL (15 minutes) with refresh tokens.

### 5.2 Rate Limiting Is Application-Level
Spam detection uses in-process counters. There is no infrastructure-level rate limiting (e.g., Nginx limit_req, Cloudflare). A sufficiently fast attacker can bypass application-level checks.

**Planned fix:** Nginx rate limiting or Cloudflare WAF in front of the API.

### 5.3 Media Files Are Publicly Accessible
Uploaded media files are served from `/media/` as static files with no authentication check. Issue photos are effectively public once uploaded.

**Design decision:** Civic issue photos are inherently public information. Anonymous reporters may still not wish their photos cross-referenced. A future privacy option would allow "blur face" post-processing.

---

## 6. Accessibility

### 6.1 Map Is Not Fully Screen-Reader Accessible
Leaflet.js map pins are SVG/Canvas elements. While ARIA labels are applied to the map container, individual pins are not individually keyboard-focusable or announced in a useful way by screen readers.

**Planned fix:** Tabular fallback view ("List View") showing all issues near the user's location, fully accessible without the map.

### 6.2 Voice Input English-Only
The Web Speech API `lang` is set to `en-IN`. Hindi, Marathi, Tamil, and other regional language voice input are not currently supported.

**Planned fix:** Language selector for speech recognition matching the user's device locale.

---

## 7. Operational

### 7.1 No Email Notification Infrastructure
The codebase references a `notification_service.py` for push notifications, but SMTP email notifications are not wired up. Notification preferences are stored but not acted upon for email.

### 7.2 No Push Notification Service
Web Push (FCM/APNS) integration is scaffolded in `notification_service.py` but not activated. Users receive real-time updates only while the app is open.

### 7.3 Predictive Hotspots Not Production-Tuned
The predictive hotspot generator uses a simple k-means-inspired cluster detection without temporal weighting. Hotspot predictions have not been validated against historical resolution data. Furthermore, new wards with fewer than 3 reported issues are excluded from hotspot calculations to prevent noise.

---

## 8. Enterprise & Platform

### 8.1 Partially Mocked Triage Agent Tools
While the ReAct loop executes successfully, some database tools utilized by the Triage Agent (e.g. looking up departmental resolution history or agent logs) return deterministic mocked values instead of querying live tables. Full database integration is deferred to v2.

### 8.2 Video Single-Frame Analysis
 Lacking a full video segmentation pipeline, video issue submissions only have their first keyframe checked by the AI for categorization. The remainder of the video is stored for human inspection but ignored during automated classification.

### 8.3 Firebase Setup Prerequisite
Push notifications require a Google Firebase Project service account JSON file, referenced by `FIREBASE_CREDENTIALS_PATH` and enabled via `FCM_ENABLED=true`. In default local developer builds, this feature is disabled.

### 8.4 Bulk Update Schema Limits
The `PATCH /admin/issues/bulk` endpoint does not enforce a maximum size limit on the array of issue IDs in Pydantic schema validation. Batching too many updates at once can lead to slow transactions.
