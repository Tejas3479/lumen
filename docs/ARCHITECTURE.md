# Lumen — System Architecture

## Overview

Lumen is a hyperlocal civic issue reporting platform designed for Indian cities. Citizens photograph and describe infrastructure problems (potholes, water leakage, broken streetlights, garbage, drainage failures, etc.); the system categorises each report with AI, routes it to the responsible ward official, and shows resolution progress publicly on a real-time map.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│   React + Vite SPA  ←→  Leaflet Map  ←→  Socket.IO-client     │
│   IndexedDB (offline queue)  |  Service Worker (PWA)           │
└────────────────────────┬────────────────────────────────────────┘
                         │  HTTPS / WSS
┌────────────────────────▼────────────────────────────────────────┐
│                      API LAYER (FastAPI)                        │
│   REST endpoints (auth, issues, comments, admin, AI, media)     │
│   Socket.IO server (python-socketio) — real-time events         │
│   Alembic migrations  |  async SQLAlchemy 2.x                   │
└──────┬──────────────────────────────┬───────────────────────────┘
       │                              │
┌──────▼──────────┐        ┌──────────▼──────────┐
│   PostgreSQL    │        │      Redis            │
│  (primary store)│        │  • Celery broker      │
│  PostGIS-ready  │        │  • AI result cache    │
│  Alembic ORM    │        │  • Socket pub/sub     │
└─────────────────┘        └──────────┬────────────┘
                                      │
                           ┌──────────▼──────────┐
                           │   Celery Worker       │
                           │  • AI categorizer     │
                           │  • Predictive hotspot │
                           │  • Notification push  │
                           └──────────┬────────────┘
                                      │
                            ┌──────────▼──────────┐
                            │  Google Gemini 3.5  │
                            │  (OpenAI fallback)  │
                            └─────────────────────┘
```

---

## Component Descriptions

### Frontend (React + Vite)
- **Map View** — Leaflet.js map showing live issue pins colour-coded by severity and status. Issues within the current viewport are fetched via `GET /issues/nearby`.
- **ReportIssueModal** — 3-step guided form: (1) category + description, (2) media upload, (3) location confirm + submit. Performs pre-submit duplicate check via `GET /issues/check-duplicates`.
- **AppStore (Zustand)** — global state for auth, map pins, pending offline drafts, gamification events.
- **Socket.IO client** — subscribes to `new_issue`, `status_update`, `ai_result`, `comment_added`, `verification_update`, `emergency_alert` events to keep the UI live.
- **Service Worker** — cache-first shell, network-first API calls, tile cache for offline map. Queues form submissions in IndexedDB when offline.

### Backend (FastAPI)
- **Routes** — `/auth`, `/issues`, `/comments`, `/votes`, `/gamification`, `/analytics`, `/admin`, `/ai`, `/media`, `/offline` — each in its own router module under `app/routes/`.
- **Services** — stateless async service functions called by routes. Each route file imports from `app/services/`.
- **Middleware** — CORS (configurable origins), global LumenException handler returning JSON with `error_code` + `message`.
- **Socket.IO** — `python-socketio` ASGIApp wrapping FastAPI. Event emitters in `app/sockets/events.py`. Redis pub/sub subscriber bridges Celery-emitted events to connected clients.

### Database (PostgreSQL)
- **Core tables** — `users`, `issues`, `issue_media`, `categories`, `status_history`, `issue_audit_log`
- **Community tables** — `verifications`, `votes`, `flags`, `comments`, `resolution_feedback`
- **Gamification tables** — `leaderboard_points`, `badges`, `user_badges`
- **Offline tables** — `offline_drafts`
- **Analytics tables** — `predictive_hotspots`
- All timestamps stored as UTC. UUIDs used as primary keys throughout.

### Redis
- **Celery broker + result backend** — task routing for AI categorisation and predictive hotspot generation.
- **AI result cache** — key `lumen:ai_result:{issue_id}`, 5-minute TTL. Serves `GET /ai/status/{id}` polling before DB hit.
- **Socket pub/sub** — Celery workers publish to Redis channels; the FastAPI startup task subscribes and re-emits to Socket.IO rooms.

### Celery Worker
- **`categorize_issue_task`** — dispatched on issue creation. Calls Google Gemini 3.5 Flash with image + description; falls back to OpenAI GPT-4o. Writes result to DB and Redis; publishes `ai_result` to Socket.IO via Redis pub/sub.
- **`generate_hotspots_task`** — periodic task (hourly) running k-means-style clustering on open issues to identify emerging trouble zones.

---

## Data Flow: Issue Creation

```
User submits form (multipart/form-data)
  → POST /issues
    1. Idempotency check (offline_draft_id)
    2. Spam check (rate limit + duplicate text)
    3. Create Issue row + StatusHistory (reported)
    4. Process + save media files (JPEG resize, thumbnail)
    5. Dispatch Celery AI task (non-blocking)
    6. Emit new_issue (+ emergency_alert if flagged) via Socket.IO
    7. Return IssueOut to client

(async, seconds later)
  Celery: categorize_issue_task
    → call Gemini 3.5 Flash (image + description)
    → parse JSON response
    → update Issue.ai_category, ai_severity, ai_confidence
    → write Redis cache key
    → publish ai_result event → Redis pub/sub → Socket.IO → client UI
```

---

## Deployment Topology

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| FastAPI | `lumen-backend` | 8000 | Backend REST API + Socket.IO server |
| Celery Worker | `lumen-worker` | — | Background task processing |
| Celery Beat | `lumen-beat` | — | Background periodic scheduler |
| PostgreSQL | `lumen-db` | 5432 | Primary data store |
| Redis | `lumen-redis` | 6379 | Message broker & cache |
| Frontend | `lumen-frontend` | 5173 | React web application |

All services run as Docker containers orchestrated via `docker-compose.yml`. Production deployment targets a single VPS behind an Nginx reverse proxy with TLS termination.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| FastAPI over Django/Flask | Native async, auto OpenAPI docs, Pydantic validation |
| SQLAlchemy async over Tortoise ORM | Mature ecosystem, Alembic migrations, PostGIS support |
| Socket.IO over raw WebSocket | Rooms, namespaces, auto-reconnect built-in |
| Redis pub/sub for Celery→Socket bridge | Celery workers cannot call Socket.IO server directly |
| UUID primary keys | Globally unique, safe to expose in URLs |
| Soft deletes for comments | Preserves thread context; avoids orphan replies |
| Idempotency keys for offline sync | Prevents duplicate issues when network re-connects |
| Trust-weighted verification | Hard (GPS) verifications carry more weight than soft ones |
