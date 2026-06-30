# Lumen — Future Scope

This document describes the planned evolution of Lumen beyond v1. Features are grouped by theme and ordered roughly by priority and implementation dependency.

---

## 1. AI Pipeline Enhancements

### 1.1 Fine-Tuned Civic Issue Model
**Goal:** Reduce Gemini API costs further and improve accuracy on Indian civic imagery.

**Approach:**
- Collect labelled training data from user corrections (`POST /ai/feedback` logs).
- Minimum viable dataset: 10,000 labelled image-category-severity triplets.
- Fine-tune a smaller vision model (e.g., Gemini Flash) using Google AI Studio fine-tuning pipelines.
- A/B test fine-tuned vs. base model on incoming submissions.
- Target: ≥ 95% top-1 category accuracy on held-out Indian civic photos.

### 1.2 Multi-Language Description Support
- Accept issue descriptions in Hindi, Marathi, Tamil, Telugu, Kannada.
- Translate to English before AI prompt to maintain consistent classification.
- Return AI explanation translated back to reporter's language.

### 1.3 Video Analysis
- Currently, uploaded videos are stored but not analysed.
- Future: extract keyframes from short videos (≤30s), run Gemini on top 3 frames.
- Audio analysis for noise/environmental complaints.

### 1.4 Severity Auto-Escalation
- Monitor issues over time; if an issue has been `assigned` for >7 days without progress, automatically escalate severity.
- Alert official and ward admin via push notification.

---

## 2. Verification Enhancements

### 2.1 Photo Re-Verification
- A third verification type: `photo_verify` — user uploads a new photo from the issue location.
- Trust weight: 0.8 (between hard and full hard).
- Server-side EXIF geolocation check to confirm photo was taken near the issue.

### 2.2 Official Verification
- Officials can perform "authoritative verification" (trust weight: 3.0).
- A single official hard-verify immediately escalates to `verified` regardless of citizen score.

### 2.3 Velocity Check (Anti-Spoofing)
- Detect impossible travel: same user performing hard verification at two locations >1km apart within 2 minutes → flag both verifications for admin review.

### 2.4 Crowdsourced Before/After
- After resolution, request a "after photo" from any community member who was a prior verifier.
- Compare with original photo using Vision API to confirm resolution.

---

## 3. Scalability and Infrastructure

### 3.1 Kubernetes Migration
- Migrate from Docker Compose to Kubernetes (K3s for single-node or GKE/EKS for cloud).
- Horizontal pod autoscaling for FastAPI workers based on request queue depth.
- Celery workers as separate Deployment scaled by queue length (KEDA).

### 3.2 PostgreSQL Read Replicas
- Primary for writes; one read replica for analytics queries and leaderboard.
- Connection pool via PgBouncer.

### 3.3 Redis Cluster
- Sentinel or Redis Cluster for HA.
- Separate Redis instances for Celery broker, cache, and Socket pub/sub.

### 3.4 Google Cloud Storage (GCS) for Media
- Migrate from local filesystem media storage to Google Cloud Storage (GCS) or S3-compatible object storage.
- Serve uploaded issue photos and videos via Google Cloud CDN to optimize mobile load times.
- Eliminate single-node disk space constraints.

### 3.5 Materialised Leaderboard
- Celery periodic task refreshes a `leaderboard_cache` table every 15 minutes.
- `GET /gamification/leaderboard` reads from cache — O(1) query regardless of user count.

### 3.6 PostgreSQL pgvector for Database-Level Similarity
- Replace the in-memory TF-IDF and Python-level semantic similarity comparisons with PostgreSQL `pgvector`.
- Store Gemini/text-embedding-004 vectors directly in the database.
- Utilize HNSW vector indexing to run sub-millisecond semantic duplicate check queries at scale.

---

## 4. Municipal Integration

### 4.1 REST Adapter for Municipal ERP
- Webhook emitter: on `status → assigned`, POST structured issue data to municipal work-order API.
- Receive status updates from ERP via inbound webhook: `PATCH /issues/{id}/status` triggered externally.
- Target integrations: SAP for Municipal Bodies, eNagarPalika, Open311 standard.

### 4.2 Ward Boundary Polygon Import
- Import official ward boundary GeoJSON from municipal GIS servers.
- Auto-assign `ward` field based on GPS coordinate falling within polygon.
- Currently: `ward` is a free-text field entered by the reporter.

### 4.3 SLA Tracking and Breach Alerts
- Per-category SLA definitions configurable by admin (e.g., potholes: 7 days, water leakage: 24 hours).
- Automatic SLA breach alerts to department heads via email/WhatsApp.
- SLA compliance rate added to dashboard.

---

## 5. Native Mobile App

### 5.1 React Native App
- Wrap the existing React components in React Native for iOS and Android.
- Unlock: background location tracking for "I'm near an issue" notifications.
- Unlock: native camera API for better photo quality and direct EXIF access.
- Unlock: FCM/APNS push notifications (replacing Web Push).

### 5.2 Offline-First Native Sync
- Native SQLite for offline queue (more robust than IndexedDB).
- Foreground sync on app resume + background sync via WorkManager/BGTaskScheduler.

---

## 6. Advanced Analytics

### 6.1 Resolution Time Prediction (ML)
- Train a regression model on `(category, severity, ward, season) → days_to_resolve`.
- Replace the heuristic ETA formula with a data-driven model.
- Show prediction confidence intervals.

### 6.2 Ward Performance Dashboard (Public)
- Public-facing dashboard showing per-ward resolution rates, average times, open vs. closed counts.
- Monthly report auto-generated as PDF and published to a public URL.

### 6.3 Heatmap Temporal Animation
- Animate the heatmap across time to show how issue density shifted week-over-week.
- Identify recurring seasonal patterns (monsoon drainage → spike every June–September).

---

## 7. Community Features

### 7.1 Issue Subscriptions
- Citizens subscribe to any issue (not just their own) to receive status updates.
- Useful for high-visibility issues that affect many people.

### 7.2 Neighbourhood Groups
- Ward-level community spaces where citizens discuss issue patterns.
- Moderated by a citizen-elected ward ambassador.

### 7.3 Resolution Recognition
- When an issue is closed, all verifiers and the original reporter receive a "Resolved!" celebration card.
- Social share button to post to WhatsApp/Twitter: "I helped fix a pothole in Ward 12! #Lumen"

### 7.4 NGO and RWA Integration
- Register Resident Welfare Associations as verified organizations.
- RWA-filed issues get a "verified organization" badge and higher initial trust weight.

---

## 8. Next-Gen Integration Channels

### 8.1 WhatsApp Reporting Bot
- Build a lightweight WhatsApp Business API integration bot.
- Citizens can snap a photo of an issue and send it via WhatsApp along with their current GPS pin.
- The backend automatically parses the photo and location, creates a draft issue in the database, and replies to the user with a tracking link.

### 8.2 IoT Sensor Integration
- Connect city IoT devices (e.g. smart water meters, smart streetlights, trash bin fill sensors) to the Lumen reporting pipeline.
- Automatically file civic issues on sensor anomalies (e.g. drop in water line pressure or bin fill level > 90%) to preempt citizen reports.
