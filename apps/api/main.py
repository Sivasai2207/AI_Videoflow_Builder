from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from database import init_db
from routers import (
    auth_router,
    projects_router,
    runs_router,
    shots_router,
    assets_router,
    plans_router,
    images_router,
    video_router,
    audio_router,
    export_router,
    qc_router,
    health_router,
    # Phase 6
    system_router,
    models_router,
    performance_router,
)

app = FastAPI(
    title="Video Generator AI",
    description="Local-first AI video generation platform",
    version="0.6.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(runs_router)
app.include_router(shots_router)
app.include_router(assets_router)
app.include_router(plans_router)
app.include_router(images_router)
app.include_router(video_router)
app.include_router(audio_router)
app.include_router(export_router)
app.include_router(qc_router)
app.include_router(health_router)
# Phase 6
app.include_router(system_router)
app.include_router(models_router)
app.include_router(performance_router)


@app.on_event("startup")
async def on_startup():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.6.0"}
