# Lumen — Deployment Guide

## Quick Start (Development)

**Prerequisites:** Docker, Docker Compose v2, OpenAI API key.

```bash
# 1. Clone the repository
git clone https://github.com/your-org/lumen.git
cd lumen

# 2. Create your environment file
cp .env.example .env

# 3. Add your OpenAI API key to .env
#    OPENAI_API_KEY=sk-...

# 4. Launch everything
./start.sh

# 5. Open the app
#    http://localhost:5173
```

The `start.sh` script handles everything automatically:
- Starts PostgreSQL and Redis
- Waits for the database to be ready
- Builds and starts the FastAPI backend
- Runs Alembic migrations (`alembic upgrade head`)
- Seeds demo data (`python seed_data.py`)
- Starts the Celery worker, Celery beat scheduler, and Vite frontend

---

## Environment Variables

See [`.env.example`](../.env.example) for the complete reference with descriptions.

**Core configuration parameters:**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing secret (64+ random characters) |
| `GOOGLE_API_KEY` | Google AI Studio API key (Gemini, text-embedding-004, geocoding) |
| `VITE_GOOGLE_MAPS_API_KEY` | Google Maps JS SDK key |
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase credentials JSON file |
| `FCM_ENABLED` | Toggle Firebase Cloud Messaging (true/false) |
| `BLUR_VARIANCE_THRESHOLD` | Laplacian variance threshold for image quality checks (default: 100.0) |
| `CORS_ORIGINS` | Commas-separated list of allowed CORS origins |

All other variables have safe defaults suitable for local development.

---

## Services Started by Docker Compose

| Service | URL / Port | Description |
|---------|-----------|-------------|
| **Frontend** (Vite dev server) | http://localhost:5173 | React + TypeScript SPA |
| **Backend** (FastAPI + Socket.IO) | http://localhost:8000 | REST API + WebSocket |
| **API Docs** (Swagger UI) | http://localhost:8000/docs | Interactive API explorer |
| **Database** (PostgreSQL 16) | localhost:5432 | Primary data store |
| **Redis** | localhost:6379 | Celery broker + result cache + Socket pub/sub |
| **Celery Worker** | background (no port) | AI categorisation + notification tasks |
| **Celery Beat** | background (no port) | Periodic scheduler (hotspot generation, etc.) |

---

## Docker Compose Services Summary

```yaml
services:
  db            # PostgreSQL 16-alpine, health-checked
  redis         # Redis 7-alpine, health-checked, AOF persistence
  backend       # FastAPI, uvicorn app.main:socket_app, port 8000
  worker        # Celery worker --concurrency=2
  beat          # Celery beat scheduler
  frontend      # Node 20-alpine, npm run dev -- --host, port 5173

volumes:
  postgres_data  # Persistent DB data
  redis_data     # Persistent Redis AOF
  media_data     # Uploaded issue photos/videos

---

## Celery Beat Schedule

Lumen's periodic background jobs are run by the `beat` scheduler container matching the following schedule:

| Task | Schedule | Purpose |
|---|---|---|
| `generate_hotspots_task` | Every 6 hours | DBSCAN hotspot prediction and clustering |
| `run_escalation_check` | Every 30 minutes | SLA breach detection and auto-escalation |
| `generate_weekly_reports` | Every Monday at 8 AM | Weekly Ward AI journalism narration |
| `cleanup_guest_users` | Daily at 3 AM | Guest user account purge (DPDP compliance) |
```

---

## Seed Data — Demo Credentials

The seed script (`backend/seed_data.py`) creates the following accounts for testing:

| Role | Email | Password |
|------|-------|----------|
| **Admin** | admin@lumen.civic | admin123 |
| **Official** (Roads) | kiran@bbmp.gov.in | official123 |
| **Official** (Water) | water.dept@bbmp.gov.in | official123 |
| **Citizen** | priya@example.com | citizen123 |
| **Citizen** | rajan@example.com | citizen123 |

The seed script also creates:
- All 6 issue categories (pothole, water_leakage, streetlight, garbage, drainage, other)
- All 10 badges
- ~200 realistic demo issues across Bengaluru wards
- Verifications, votes, comments, and gamification points

---

## Useful Commands

```bash
# View logs for a service
docker compose logs -f backend
docker compose logs -f worker

# Re-run migrations only
docker compose exec backend alembic upgrade head

# Re-seed the database
docker compose exec backend python seed_data.py

# Open a PostgreSQL shell
docker compose exec db psql -U lumen -d lumen

# Open a Redis CLI
docker compose exec redis redis-cli

# Rebuild a single service after code changes
docker compose up -d --build backend

# Check service health
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

---

## Health and Monitoring Endpoints

Lumen provides detailed JSON health endpoints for uptime checkers, load balancers, and monitoring tools:

* **GET `/health`**
  - **Purpose:** Simple ping check to verify the HTTP server is accepting requests.
  - **Response (200 OK):** `{"status": "healthy", "app": "Lumen"}`

* **GET `/health/ready`**
  - **Purpose:** Deep readiness check that attempts connectivity to PostgreSQL, Redis, and Celery.
  - **Response (200 OK):** Detailed status per check. Returns `503 Service Unavailable` on database or broker disconnect.

* **GET `/health/metrics`**
  - **Purpose:** Exposes live metrics including open issue counts per status, database connection pool statistics, and active workers.
  - **Response (200 OK):** JSON dict of metrics.

---

---

## Stopping the Stack

```bash
# Stop all services (data volumes preserved)
docker compose down

# Stop all services AND remove all data volumes
docker compose down -v
```

---

## Production Considerations

> The hackathon build uses development defaults. Before deploying to production, address the following:

| Area | Development Default | Production Recommendation |
|------|--------------------|-----------------------------|
| **Server** | `uvicorn --reload` | Gunicorn with uvicorn workers (`gunicorn -w 4 -k uvicorn.workers.UvicornWorker`) |
| **Frontend** | Vite dev server | Build with `npm run build`, serve via Nginx |
| **Media storage** | Local filesystem (`./media`) | S3-compatible object storage (MinIO, AWS S3) + CDN |
| **Debug mode** | `DEBUG=true` | `DEBUG=false` |
| **Secret key** | Placeholder in `.env.example` | 64+ random characters (`openssl rand -hex 32`) |
| **CORS** | `localhost:5173` | Specific production domain(s) only |
| **SSL** | None | Nginx + Let's Encrypt (Certbot) |
| **Database** | Single container | Managed PostgreSQL (RDS, Cloud SQL) with backups |
| **Redis** | Single container | Managed Redis (ElastiCache, Memorystore) with HA |
| **Rate limits** | Permissive defaults | Tune `RATE_LIMIT_*` env vars; add Nginx `limit_req` |
| **Logging** | stdout JSON | Ship to log aggregation (Loki, Datadog, CloudWatch) |
| **Monitoring** | Health endpoints only | Add uptime monitoring + alerting on `/health/ready` |

---

## Backend Dockerfile Entrypoint

The backend `CMD` runs the Socket.IO ASGI wrapper — **not** the bare FastAPI `app` object. This is required for WebSocket support:

```dockerfile
CMD ["uvicorn", "app.main:socket_app", "--host", "0.0.0.0", "--port", "8000"]
```

`socket_app` is defined in `app/main.py` as:
```python
socket_app = socketio.ASGIApp(sio, app)
```

Using `app.main:app` instead of `app.main:socket_app` will cause all Socket.IO connections to fail silently.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Backend exits immediately on startup | Database not ready | `docker compose logs db` — check health |
| `ModuleNotFoundError` in backend | Requirements not installed | `docker compose up -d --build backend` |
| AI tasks not processing | Celery worker down or Redis unreachable | `docker compose ps worker` |
| WebSocket disconnects immediately | Wrong ASGI entrypoint (`app` instead of `socket_app`) | Verify Dockerfile `CMD` |
| Media files return 404 | Volume mount mismatch | Check `MEDIA_PATH` vs. Docker volume |
| Alembic migration fails on startup | Schema drift from incomplete prior migration | `docker compose exec backend alembic history` |
| Seed script fails | Database already seeded | Safe to ignore — seed is idempotent for categories and badges |
| Frontend shows "Cannot connect to API" | Backend not yet healthy | Wait for `docker compose ps` to show backend as healthy |
