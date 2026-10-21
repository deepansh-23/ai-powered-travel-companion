"""AI Powered Travel Companion - FastAPI Main Application.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.routes import (
    health,
    places,
    cafes,
    medical,
    itinerary,
    area,
    route,
    history,
    export,
    transport,
    hotel,
    captcha,
    feedback,
    auth,
    sessions,
    settings as public_settings,
)
from app.db import dispose_db, init_db
from admin.routes import router as admin_router
from admin.monitoring import ApiMetricsMiddleware
from app.services.site_settings_guard import MaintenanceModeMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()      # connect to PostgreSQL and create tables (never blocks startup on failure)
    yield
    await dispose_db()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Full-stack AI-assisted local discovery platform, itinerary planner, and map explorer API.",
    lifespan=lifespan
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Maintenance mode (admin setting) — added BEFORE metrics so 503s are still recorded
app.add_middleware(MaintenanceModeMiddleware)
# API Metrics Middleware for Admin Monitoring
app.add_middleware(ApiMetricsMiddleware)

# Register API Routers
app.include_router(health.router)
app.include_router(places.router)
app.include_router(cafes.router)
app.include_router(medical.router)
app.include_router(itinerary.router)
app.include_router(area.router)
app.include_router(route.router)
app.include_router(history.router)
app.include_router(export.router)
app.include_router(transport.router)
app.include_router(hotel.router)
app.include_router(captcha.router)
app.include_router(feedback.router)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(public_settings.router)
app.include_router(admin_router)


# Mount frontend directory for seamless local single-command running
# Admin static files are served under /admin (isolated from main frontend)
admin_frontend_path = settings.FRONTEND_DIR / "admin"
if admin_frontend_path.exists():
    app.mount("/admin", StaticFiles(directory=str(admin_frontend_path), html=True), name="admin_frontend")

frontend_path = settings.FRONTEND_DIR
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
