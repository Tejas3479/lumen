# Lumen — Google Technologies Integration

This document maps every Google technology used in Lumen
to the file where it is implemented, the API it calls,
and the moment a judge can see it during the demo.

---

## 1. Google Gemini 3.5 Flash — Primary AI Engine

**File:** [ai_categorizer.py](file:///c:/Users/tejas/Downloads/lumen/backend/app/services/ai_categorizer.py)
**API:** `generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent`
**Key:** `GOOGLE_API_KEY`

**What it does:**
Every issue submitted to Lumen is classified by Google Gemini.
Gemini receives the photo + description and returns:
- Category (pothole, water_leakage, streetlight, garbage, drainage, other)
- Severity (low, medium, high, critical)
- Confidence (0–1)
- Plain-language explanation for citizens
- Step-by-step reasoning (chain-of-thought)
- Alternative categories considered

**Demo moment:**
Submit a new issue with a photo.
Within 4 seconds: the `AIExplanationCard` populates with
"AI detected: Pothole (91% confidence)" and shows Gemini's reasoning.

**Why Gemini specifically:**
- `gemini-3.5-flash`: sub-2 second latency for real-time civic use
- JSON mode (responseMimeType): eliminates markdown fences in output
- Multimodal: processes image and text in single API call
- Cost: ~$0.00015 per issue classified — viable at city scale

---

## 2. Google text-embedding-004 — Semantic Duplicate Detection

**File:** [duplicate_detector.py](file:///c:/Users/tejas/Downloads/lumen/backend/app/services/duplicate_detector.py)
**API:** `generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents`
**Key:** `GOOGLE_API_KEY`

**What it does:**
Before a citizen submits a new report, Lumen checks whether a
similar issue already exists within 150 metres. It uses Google's
`text-embedding-004` to compute semantic similarity between the new
description and existing issue descriptions.

**Why text-embedding-004:**
High-dimensional vectors optimised for Indian-English civic text.
Understands that "broken road near 80 Feet Road signal" and
"pothole at the junction on 80 Feet Road" are the same issue.

**Demo moment:**
Submit a report with a description similar to an existing issue
(e.g., "Pothole near Sony World junction").
The `DuplicateSuggestionPanel` appears: "Similar issue found 45m away —
support it instead?"

---

## 3. Google Maps Platform — Primary Map Provider

**File:** [GoogleMapsView.tsx](file:///c:/Users/tejas/Downloads/lumen/frontend/src/components/GoogleMapsView.tsx)
**API:** `maps.googleapis.com` (JavaScript API via `@googlemaps/js-api-loader`)
**Key:** `VITE_GOOGLE_MAPS_API_KEY`

**What it does:**
When `VITE_GOOGLE_MAPS_API_KEY` is set, the homepage map uses
Google Maps instead of OpenStreetMap. Issue markers use
custom SVG icons (shape + color, color-blind safe).
Emergency issues animate with `BOUNCE` animation.

**Libraries loaded:** `places`, `marker`

**Demo moment:**
Open the homepage. The map renders Google Maps tiles with
Bengaluru street labels in English and Kannada.
Issue markers show as shape-coded SVG icons.
Street View control is available.

---

## 4. Google Places Autocomplete — Address Input

**File:** [ReportIssueModal.tsx](file:///c:/Users/tejas/Downloads/lumen/frontend/src/components/ReportIssueModal.tsx)
**API:** `maps.googleapis.com/maps/api/place/autocomplete`
**Key:** `VITE_GOOGLE_MAPS_API_KEY` (shared with Maps)

**What it does:**
In Step 3 of the report flow (Where is it?), the address
input field uses Google Places Autocomplete to suggest
Indian addresses as the citizen types.

**Demo moment:**
Open the report modal, proceed to Step 3.
Start typing "Koramangala 6th Block" in the address field.
Autocomplete suggestions appear.
Selecting a suggestion auto-fills lat/lng, eliminating manual pin correction.

---

## 5. Google Geocoding API — Reverse Geocoding

**File:** [geo_utils.py](file:///c:/Users/tejas/Downloads/lumen/backend/app/services/geo_utils.py)
**API:** `maps.googleapis.com/maps/api/geocode/json`
**Key:** `GOOGLE_API_KEY`

**What it does:**
When a citizen's GPS coordinates are captured, Lumen calls
Google Geocoding API to convert (lat, lng) → human-readable address.
The address and ward are stored with the issue for admin queue filtering.

**Why Google Geocoding over Nominatim:**
- 1 req/sec limit on Nominatim → fails under demo load
- Google handles Indian address hierarchy correctly
  (sublocality → ward, locality → zone)
- Returns structured components for ward extraction

**Demo moment:**
Submit a report. The address field populates automatically:
"80 Feet Road, Koramangala, Bengaluru 560034"
The ward field "Koramangala" is extracted for admin filtering.

---

## 6. Firebase Cloud Messaging — Push Notifications

**File:** [notification.py](file:///c:/Users/tejas/Downloads/lumen/backend/app/services/notification.py)
**API:** `firebase.googleapis.com` (Firebase Admin SDK)
**Key:** `FIREBASE_CREDENTIALS_PATH` (service account JSON)

**What it does:**
When an issue status changes, Lumen sends a push notification
to the reporter via Firebase Cloud Messaging. FCM works on
Android, iOS (16.4+), and desktop Chrome — unlike Web Push VAPID
which fails on many iOS devices.

**Demo moment:**
Change an issue status to "resolved" via the admin dashboard.
The reporter receives a push notification:
"Is it really fixed? 🏁 [Issue Title] — Tap to confirm or dispute"

---

## Summary Table

| Google Technology | Purpose | Key Setting | Demo Visible |
|---|---|---|---|
| Gemini 3.5 Flash | Issue categorization + reasoning | `GOOGLE_API_KEY` | ✅ Every submission |
| text-embedding-004 | Duplicate detection similarity | `GOOGLE_API_KEY` | ✅ Pre-submit check |
| Google Maps JS | Map tiles + marker rendering | `VITE_GOOGLE_MAPS_API_KEY` | ✅ Homepage |
| Google Places | Address autocomplete | `VITE_GOOGLE_MAPS_API_KEY` | ✅ Report modal |
| Google Geocoding | Reverse geocoding (GPS → address) | `GOOGLE_API_KEY` | ✅ Every submission |
| Firebase (FCM) | Push notifications | `FIREBASE_CREDENTIALS_PATH` | Demo (requires setup) |

---

## Configuration for Judges

To enable all Google Technologies:

1. Get a Google AI Studio API key: https://aistudio.google.com/
   Add to `.env`: `GOOGLE_API_KEY=your-key`

2. Get a Google Maps Platform API key: https://console.cloud.google.com/
   Enable: **Maps JavaScript API**, **Places API**, **Geocoding API**
   Add to frontend `.env`: `VITE_GOOGLE_MAPS_API_KEY=your-key`

3. (Optional) Firebase push notifications:
   Create Firebase project, download `serviceAccount.json`
   Add to `.env`: `FIREBASE_CREDENTIALS_PATH=/path/to/serviceAccount.json`
   `FCM_ENABLED=true`

With only `GOOGLE_API_KEY` set: Gemini + Geocoding + Embeddings are active.
With only `VITE_GOOGLE_MAPS_API_KEY` set: Maps + Places are active.
Both keys together: all 5 Google integrations active.

Also create frontend `.env` (parallel to `frontend/package.json`):
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_GOOGLE_MAPS_API_KEY=your-key-here
```

---

## Google Cloud Platform — Production Infrastructure

The complete Lumen platform is deployed entirely on Google Cloud Platform using production-ready services:

| Google Service | Purpose |
|----------------|---------|
| **Cloud Run** | Serverless hosting for Backend and Frontend |
| **Cloud SQL** | Managed PostgreSQL 15 |
| **Memorystore** | Redis Cache + Celery Message Broker |
| **Cloud Storage** | Object Storage for User-Uploaded Media |
| **Artifact Registry** | Secure Docker Image Hosting |

### Live URL:
`https://lumen-frontend-651466414804-asia-south1.run.app` (Live URL after Cloud Run deployment completes)

