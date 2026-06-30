# Lumen — Community Hero 🌟

> **Hyperlocal civic issue reporting platform for Indian cities.**
> Report infrastructure problems, verify with neighbours, track resolutions, earn badges.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev)

---

## 👨‍⚖️ For Hackathon Judges

Open: **http://localhost:5173/?judge=true**

The guided feature tour will start automatically on the map centered on **Bengaluru**, walking you through:
1. 📸 AI-powered issue reporting (Google Gemini 3.5 Flash)
2. 🤖 Autonomous Triage Agent (Gemini Function Calling)
3. ✓ Community verification system (hard/soft)
4. 📶 Offline-first PWA
5. 🛡️ Admin dashboard with AI recommendations

* **AI Agents Status Endpoint:** `GET http://localhost:8000/ai/agents/status`  
* **Admin Login:** `admin@lumen.civic` / `admin123`  
* **Citizen Login:** `priya@example.com` / `citizen123`  

To restart the tour: add `?judge=true` to any URL.

---

## Quick Start (5 steps)

**Prerequisites:** Docker Desktop, Docker Compose v2, a Google AI Studio API key (primary) or OpenAI API key (fallback).

```bash
# 1. Clone the repository
git clone https://github.com/Tejas3479/lumen.git
cd lumen

# 2. Create your environment file
cp .env.example .env

# 3. Add your Google API key
#    Open .env and set: GOOGLE_API_KEY=AIzaSy...

# 4. Start the full stack (builds, migrates, seeds, launches)
chmod +x start.sh
./start.sh

# 5. Open the app
#    http://localhost:5173
```

### Demo Login Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@lumen.civic | admin123 |
| Official | kiran@bbmp.gov.in | official123 |
| Citizen | priya@example.com | citizen123 |
| Citizen | rajan@example.com | citizen123 |

---

## What You Can Demo

1. **Report an issue** — tap the FAB, take a photo, confirm location, submit
2. **AI categorisation** — result appears in ~10 seconds via WebSocket
3. **Community verification** — hard (GPS) or soft verify any reported issue
4. **Admin queue** — login as admin, see emergencies first, bulk-update statuses
5. **Resolution flow** — mark resolved, citizen confirms or disputes, 3 disputes reopen
6. **Gamification** — earn points and badges, climb the leaderboard
7. **Predictive hotspots** — `/predictions` shows DBSCAN clusters on the heatmap
8. **Offline mode** — throttle network to Offline, submit a report, reconnect — it syncs

---

## Agent Status API
Lumen exposes a real-time health and metrics endpoint for all AI agents:
`GET http://localhost:8000/ai/agents/status`

This returns live metadata, frequency schedules, patterns, and run metrics (e.g., active escalations, reports generated) for the Triage, Proactive Escalation, and Weekly Ward Report Agents.

---

## Service URLs

| Service | URL |
|---------|-----|
| **Frontend** (Vite SPA) | http://localhost:5173 |
| **Backend API** (FastAPI) | http://localhost:8000 |
| **API Docs** (Swagger) | http://localhost:8000/docs |
| **PostgreSQL** | localhost:5432 |
| **Redis** | localhost:6379 |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.111, Python 3.11, SQLAlchemy 2 (async) |
| Database | PostgreSQL 16, Alembic migrations |
| Queue | Celery 5 + Redis 7 |
| Real-time | Socket.IO (python-socketio + socket.io-client) |
| AI | Google Gemini 3.5 Flash (primary), OpenAI GPT-4o (fallback), `text-embedding-004` (duplicate detection) |
| Push Notifications | Firebase Admin SDK (`firebase-admin`), Web Push (`pywebpush`) |
| Frontend | React 18, TypeScript 5, Vite 5 |
| State | Zustand 4 |
| Maps | Leaflet.js 1.9 + `@googlemaps/js-api-loader` + `react-leaflet` |
| Auth | JWT (python-jose) + bcrypt |
| Offline | Service Worker + IndexedDB + Background Sync API |
| Tests | pytest + pytest-asyncio + Playwright |

---

## Environment Variables

The following key configuration values are defined and documented in `.env.example`:
* `GOOGLE_API_KEY`: API key for Google Gemini model generation, text embeddings, and reverse geocoding.
* `VITE_GOOGLE_MAPS_API_KEY`: Google Maps Platform JS API key.
* `FIREBASE_CREDENTIALS_PATH`: Path to private credentials JSON for Firebase Admin SDK.
* `FCM_ENABLED`: Toggles Firebase push notifications (true/false).
* `BLUR_VARIANCE_THRESHOLD`: Laplacian variance threshold below which photos are rejected as blurry (default: 100.0).
* `CORS_ORIGINS`: Allowed CORS origin list.

---

## Agentic AI Architecture

Lumen incorporates an advanced multi-agent AI system powered by Google Gemini to automate complex municipal workflows:

1. **Issue Triage Agent**: Uses a ReAct reasoning framework with Gemini function calling to analyze issues, query spatial neighbors/backlogs, suggest classifications, priority levels, and routing actions.
2. **Proactive Escalation Agent**: Runs autonomously every 30 minutes via Celery Beat to monitor unresolved issues against category-specific SLAs, raising urgency levels and alerting officials.
3. **Weekly Ward Report Agent**: Triggers every Monday at 8 AM via Celery Beat, utilizing Gemini 3.5 Flash structured output mode to generate plain-language journalistic weekly reports for active wards.

For more details, see [AGENTIC_ARCHITECTURE.md](docs/AGENTIC_ARCHITECTURE.md).

---

## Project Structure

```
lumen/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + Socket.IO ASGI entrypoint
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── models.py            # SQLAlchemy ORM — 19 tables
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── routes/              # API endpoints (one file per domain)
│   │   │   ├── auth.py          # /auth + /users
│   │   │   ├── issues.py        # /issues (CRUD + status + verify + flag)
│   │   │   ├── comments.py      # /comments
│   │   │   ├── votes.py         # /votes
│   │   │   ├── gamification.py  # /gamification (leaderboard, me, badges)
│   │   │   ├── analytics.py     # /analytics (dashboard, heatmap, ETA)
│   │   │   ├── admin.py         # /admin (queue, bulk, export, users)
│   │   │   ├── ai.py            # /ai (status, feedback, recategorize)
│   │   │   ├── media.py         # /media (upload, delete)
│   │   │   └── offline.py       # /offline (batch sync + status)
│   │   ├── services/            # Business logic (no HTTP)
│   │   │   ├── ai_categorizer.py
│   │   │   ├── auth_service.py
│   │   │   ├── duplicate_detector.py
│   │   │   ├── escalation_agent.py
│   │   │   ├── gamification.py
│   │   │   ├── geo_utils.py
│   │   │   ├── issue_service.py
│   │   │   ├── maintenance.py
│   │   │   ├── moderation.py
│   │   │   ├── notification.py
│   │   │   ├── predictive.py
│   │   │   ├── spam_detector.py
│   │   │   ├── triage_agent.py
│   │   │   ├── verification_service.py
│   │   │   └── ward_report_agent.py
│   │   └── sockets/
│   │       └── events.py        # 13 Socket.IO event emitters + Redis bridge
│   ├── alembic/                 # Database migrations
│   ├── tests/                   # pytest test suite (22 files)
│   ├── seed_data.py             # Demo dataset loader
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/          # Reusable UI (60+ components)
│       ├── pages/               # 8 route pages
│       ├── store/               # Zustand state (appStore, issueStore, userStore)
│       ├── hooks/               # useSocket, useApi, useOffline, etc.
│       ├── lib/                 # Axios client, Socket.IO client
│       └── types/               # Shared TypeScript types
├── docs/                        # 16 documentation files
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   ├── DEPLOYMENT.md
│   └── ...
├── docker-compose.yml           # Full stack (6 services)
├── start.sh                     # One-command startup script
├── .env.example                 # All env vars documented
└── LICENSE
```

---

## Development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env       # configure .env
alembic upgrade head
python seed_data.py
uvicorn app.main:socket_app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev

# Celery worker (separate terminal, from backend/)
celery -A app.celery_app worker --loglevel=info --concurrency=2
```

---

## Running Tests

```bash
# Backend tests
cd backend
pytest tests/ -v --tb=short

# Backend tests with coverage
pytest --cov=app --cov-report=html

# E2E tests (requires running app)
cd frontend
npx playwright install --with-deps
npm run test:e2e
```

---

## Useful Commands

```bash
# View logs
docker compose logs -f backend
docker compose logs -f worker

# Re-run migrations
docker compose exec backend alembic upgrade head

# Re-seed database
docker compose exec backend python seed_data.py

# Open PostgreSQL shell
docker compose exec db psql -U lumen -d lumen

# Stop all services
docker compose down

# Stop and delete all data volumes
docker compose down -v
```

---

## Key Features by Domain

| Domain | Features |
|--------|----------|
| **Reporting** | Multipart form, photo/video/voice, duplicate pre-check, offline queue |
| **AI** | Gemini 3.5 Flash primary, GPT-4o fallback, 6 categories, 4 severities, RLHF feedback |
| **Verification** | Hard (GPS, 100m radius) + soft, trust-weighted score, auto-upgrade at 2.0 |
| **Status workflow** | 7 states, validated transitions, dispute → auto-reopen at 3 disputes |
| **Gamification** | Points, 10 badges, levels, 7-day streaks, leaderboard (all-time/monthly/weekly) |
| **Analytics** | Resolution rate, MTTR, per-category bars, top wards, DBSCAN hotspots |
| **Admin** | Emergency-first queue, bulk update, CSV/JSON export, flag moderation, user ban |
| **Offline** | Service worker, IndexedDB drafts, Background Sync, idempotency keys |
| **Real-time** | 13 Socket.IO events, Redis pub/sub bridge for Celery workers |
| **Accessibility** | WCAG 2.1 AA, voice input, high contrast, font size, keyboard nav, ARIA |

---

## Documentation

All 14 documentation files are in [`docs/`](docs/):

| File | Contents |
|------|----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System components, data flow, design decisions |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | All 40+ endpoints with request/response schemas |
| [AI_PIPELINE.md](docs/AI_PIPELINE.md) | GPT-4V pipeline, prompt design, fallback chain |
| [VERIFICATION_SYSTEM.md](docs/VERIFICATION_SYSTEM.md) | Trust weights, Haversine, auto-upgrade logic |
| [OFFLINE_SYSTEM.md](docs/OFFLINE_SYSTEM.md) | Service worker strategies, IndexedDB schema |
| [GAMIFICATION.md](docs/GAMIFICATION.md) | Points table, levels, badges, streaks |
| [ADMIN_WORKFLOW.md](docs/ADMIN_WORKFLOW.md) | Status machine, bulk actions, audit trail |
| [ACCESSIBILITY.md](docs/ACCESSIBILITY.md) | WCAG 2.1 AA implementation details |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker Compose, Nginx, CI/CD, production checklist |
| [TESTING.md](docs/TESTING.md) | Test inventory, coverage targets, run commands |
| [USER_JOURNEYS.md](docs/USER_JOURNEYS.md) | 7 end-to-end user journeys |
| [LIMITATIONS.md](docs/LIMITATIONS.md) | Known gaps and planned fixes |
| [FUTURE_SCOPE.md](docs/FUTURE_SCOPE.md) | Roadmap: fine-tuning, K8s, municipal ERP |
| [PROBLEM_STATEMENT_ALIGNMENT.md](docs/PROBLEM_STATEMENT_ALIGNMENT.md) | Why Lumen solves the civic reporting gap |

---

## License

[MIT](LICENSE) © 2026 Lumen Civic Technologies
