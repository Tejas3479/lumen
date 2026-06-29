#!/usr/bin/env bash
# =============================================================
# Lumen Start Script
# Starts all services, runs migrations, and seeds the database.
# =============================================================
set -euo pipefail

RESET='\033[0m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'

info()    { echo -e "${BLUE}[INFO]${RESET} $1"; }
success() { echo -e "${GREEN}[OK]${RESET}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1"; }
error()   { echo -e "${RED}[ERR]${RESET}  $1"; exit 1; }

# ─── Load .env ────────────────────────────────────────────────
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
  info "Loaded .env"
else
  warn ".env not found — copying from .env.example"
  cp .env.example .env
  warn "Please update .env with your values before running in production"
fi

# ─── Check dependencies ───────────────────────────────────────
command -v docker >/dev/null 2>&1 || error "Docker not installed"
command -v docker compose >/dev/null 2>&1 || error "Docker Compose (v2) not installed"

# ─── Start infrastructure ─────────────────────────────────────
info "Starting infrastructure services (db, redis)..."
docker compose up -d db redis

info "Waiting for database to be ready..."
for i in $(seq 1 30); do
  if docker compose exec db pg_isready -U lumen -d lumen >/dev/null 2>&1; then
    success "Database is ready"
    break
  fi
  sleep 2
  if [ $i -eq 30 ]; then
    error "Database did not become ready in time"
  fi
done

# ─── Build and start backend ──────────────────────────────────
info "Building and starting backend..."
docker compose up -d --build backend

info "Waiting for backend health check..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    success "Backend is healthy"
    break
  fi
  sleep 3
  if [ $i -eq 20 ]; then
    warn "Backend health check timed out — check logs with: docker compose logs backend"
  fi
done

# ─── Run Alembic migrations ───────────────────────────────────
info "Running database migrations..."
docker compose exec backend alembic upgrade head
success "Migrations complete"

# ─── Seed database ────────────────────────────────────────────
info "Seeding database..."
docker compose exec backend python seed_data.py || warn "Seed skipped (may already be seeded)"

# ─── Start remaining services ─────────────────────────────────
info "Starting Celery worker, beat, and frontend..."
docker compose up -d worker beat frontend

success "Lumen is running!"
echo ""
echo -e "  ${GREEN}Frontend:${RESET} http://localhost:5173"
echo -e "  ${GREEN}API:${RESET}      http://localhost:8000"
echo -e "  ${GREEN}API Docs:${RESET} http://localhost:8000/docs"
echo ""
echo "To stop: docker compose down"
echo "To view logs: docker compose logs -f [service]"
