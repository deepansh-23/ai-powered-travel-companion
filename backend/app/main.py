"""Smart Local Guide - FastAPI Main Application.
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
    sessions
)
from app.db import dispose_db, init_db


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


# Mount frontend directory for seamless local single-command running
frontend_path = settings.FRONTEND_DIR
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
