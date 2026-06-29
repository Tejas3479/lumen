"""
Lumen FastAPI Application
Main entry point. Mounts all routes, Socket.IO, and middleware.
"""
import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import os

from app.config import settings
from app.logging_config import setup_logging, logger
from app.exceptions import LumenException
from app.sockets.events import sio

# Route imports — all start as stubs in Session 1, filled in later sessions
from app.routes import (
    auth,
    issues,
    comments,
    votes,
    gamification,
    analytics,
    admin,
    ai,
    media,
    offline,
)

# Setup structured logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Lumen API",
    description="Community Hero — Hyperlocal Problem Solver",
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests larger than MAX_REQUEST_SIZE bytes.
    Prevents memory exhaustion from oversized request bodies.
    Does NOT apply to media upload routes (handled by individual endpoints).
    """
    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_REQUEST_SIZE:
            return Response(
                content='{"error_code": "REQUEST_TOO_LARGE", "message": "Request body exceeds 10MB limit"}',
                status_code=413,
                media_type="application/json",
            )
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware)

# Register routes
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.router, prefix="/users", tags=["users"])  # /users/me/settings
app.include_router(issues.router, prefix="/issues", tags=["issues"])
app.include_router(comments.router, prefix="/comments", tags=["comments"])
app.include_router(votes.router, prefix="/votes", tags=["votes"])
app.include_router(gamification.router, prefix="/gamification", tags=["gamification"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
app.include_router(media.router, prefix="/media", tags=["media"])
app.include_router(offline.router, prefix="/offline", tags=["offline"])

# Static media files
os.makedirs(settings.media_path, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_path), name="media")


# Global exception handler
@app.exception_handler(LumenException)
async def lumen_exception_handler(request: Request, exc: LumenException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", extra={"error": str(exc), "path": str(request.url.path)})
    return JSONResponse(
        status_code=500,
        content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


# Health endpoints
@app.get("/health", tags=["observability"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.get("/health/ready", tags=["observability"])
async def readiness_check():
    """
    Checks DB, Redis, and Celery worker connectivity.
    Returns 200 if all critical services are healthy.
    Returns 503 if any critical service is down.
    """
    checks = {}

    # Database check
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    # Redis check
    if settings.environment == "testing":
        checks["redis"] = "ok"
    else:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {str(e)[:50]}"

    # Celery worker check (inspect ping)
    if settings.environment == "testing":
        checks["celery"] = "ok"
    else:
        try:
            import asyncio
            from app.celery_app import celery_app
            inspector = celery_app.control.inspect(timeout=2)
            # Run in thread to avoid blocking the event loop
            ping_result = await asyncio.get_event_loop().run_in_executor(
                None, inspector.ping
            )
            checks["celery"] = "ok" if ping_result else "no_workers"
        except Exception as e:
            checks["celery"] = f"error: {str(e)[:50]}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
            "version": settings.app_version,
        },
    )


@app.get("/health/metrics", tags=["observability"])
async def get_metrics():
    """
    Basic operational metrics. Not a replacement for Prometheus.
    Used by hackathon judges to see live system state.
    """
    from app.database import engine
    from sqlalchemy import text

    metrics: dict = {}
    try:
        async with engine.connect() as conn:
            # Issue counts by status
            result = await conn.execute(
                text("SELECT status, COUNT(*) FROM issues GROUP BY status")
            )
            metrics["issues_by_status"] = {row[0]: row[1] for row in result.all()}

            # Total verifications
            result = await conn.execute(text("SELECT COUNT(*) FROM verifications"))
            metrics["total_verifications"] = result.scalar_one()

            # Active users in last 24 h
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM users "
                    "WHERE last_active_date >= CURRENT_DATE - 1"
                )
            )
            metrics["active_users_24h"] = result.scalar_one()

            # Connection pool stats
            metrics["db_pool"] = {
                "size": engine.pool.size(),
                "checked_out": engine.pool.checkedout(),
            }
    except Exception as e:
        metrics["error"] = str(e)

    return metrics


@app.on_event("startup")
async def startup_event():
    logger.info("Lumen API starting", extra={"environment": settings.environment})
    # Start the Redis pub/sub subscriber as a background task.
    # This bridges Celery worker events (ai_result, leaderboard_update,
    # hotspot_update) to connected Socket.IO clients.
    import asyncio
    from app.sockets.events import start_redis_subscriber
    asyncio.create_task(start_redis_subscriber(settings.redis_url))
    logger.info("Redis subscriber started")

    # Verify Redis connectivity at startup
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await r.ping()
        await r.aclose()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.warning("Redis unavailable at startup", error=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Lumen API shutting down")


# Wrap FastAPI with Socket.IO ASGI
# The object uvicorn runs is socket_app, not app
# CMD: uvicorn app.main:socket_app --host 0.0.0.0 --port 8000
socket_app = socketio.ASGIApp(sio, app)
