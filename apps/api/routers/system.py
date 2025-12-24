"""
System Router

API endpoints for system diagnostics, setup, and configuration.
"""
import os
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from dependencies import DbSession
from models.system_model import (
    SystemSettings, RendererTarget, CleanupPolicy,
    Model, ModelStatus,
)
from services.model_manager import get_system_settings, get_missing_models

router = APIRouter(prefix="/system", tags=["system"])


# ============================================================================
# Request/Response Models
# ============================================================================

class DiagnosticsResponse(BaseModel):
    """System diagnostics response."""
    disk_space_gb: float
    disk_free_gb: float
    disk_usage_percent: float
    comfyui_status: str
    redis_status: str
    ollama_status: str
    models_installed: int
    models_missing: int
    setup_completed: bool


class SetupRequest(BaseModel):
    """Setup configuration request."""
    storage_root_path: Optional[str] = None
    comfyui_url: Optional[str] = None
    redis_url: Optional[str] = None
    ollama_url: Optional[str] = None
    comfyui_models_path: Optional[str] = None


class RendererRequest(BaseModel):
    """Renderer target request."""
    default_target: str = Field(pattern="^(local_comfyui|remote_gpu_worker)$")
    remote_worker_url: Optional[str] = None


# ============================================================================
# Diagnostics
# ============================================================================

@router.get("/diagnostics")
async def get_diagnostics(session: DbSession) -> DiagnosticsResponse:
    """Get system diagnostics."""
    settings = get_system_settings(session)
    
    # Disk space
    storage_path = Path(settings.storage_root_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    
    total, used, free = shutil.disk_usage(storage_path)
    disk_space_gb = total / (1024 ** 3)
    disk_free_gb = free / (1024 ** 3)
    disk_usage_percent = (used / total) * 100
    
    # Service health checks
    comfyui_status = await check_comfyui_status(settings.comfyui_url)
    redis_status = check_redis_status(settings.redis_url)
    ollama_status = await check_ollama_status(settings.ollama_url)
    
    # Model counts
    all_models = list(session.exec(select(Model)).all())
    models_installed = len([m for m in all_models if m.status == ModelStatus.INSTALLED])
    models_missing = len([m for m in all_models if m.status != ModelStatus.INSTALLED])
    
    return DiagnosticsResponse(
        disk_space_gb=round(disk_space_gb, 2),
        disk_free_gb=round(disk_free_gb, 2),
        disk_usage_percent=round(disk_usage_percent, 1),
        comfyui_status=comfyui_status,
        redis_status=redis_status,
        ollama_status=ollama_status,
        models_installed=models_installed,
        models_missing=models_missing,
        setup_completed=settings.setup_completed,
    )


async def check_comfyui_status(url: str) -> str:
    """Check ComfyUI status."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/system_stats")
            if response.status_code == 200:
                return "online"
            return "error"
    except Exception:
        return "offline"


def check_redis_status(url: str) -> str:
    """Check Redis status."""
    try:
        from redis import Redis
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        r = Redis(host=parsed.hostname or "localhost", port=parsed.port or 6379)
        r.ping()
        return "online"
    except Exception:
        return "offline"


async def check_ollama_status(url: str) -> str:
    """Check Ollama status."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/tags")
            if response.status_code == 200:
                return "online"
            return "error"
    except Exception:
        return "offline"


# ============================================================================
# Setup
# ============================================================================

@router.post("/setup/run")
async def run_setup(
    request: SetupRequest,
    session: DbSession,
):
    """Run guided setup and save configuration."""
    from datetime import datetime
    from services.model_manager import seed_required_models, auto_detect_models
    
    settings = get_system_settings(session)
    
    # Update settings
    if request.storage_root_path:
        settings.storage_root_path = request.storage_root_path
        Path(request.storage_root_path).mkdir(parents=True, exist_ok=True)
    
    if request.comfyui_url:
        settings.comfyui_url = request.comfyui_url
    
    if request.redis_url:
        settings.redis_url = request.redis_url
    
    if request.ollama_url:
        settings.ollama_url = request.ollama_url
    
    if request.comfyui_models_path:
        settings.comfyui_models_path = request.comfyui_models_path
    
    # Seed required models
    seed_required_models(session)
    
    # Auto-detect models if path provided
    detection_result = None
    if request.comfyui_models_path:
        detection_result = auto_detect_models(session, request.comfyui_models_path)
    
    # Run diagnostics
    comfyui_status = await check_comfyui_status(settings.comfyui_url)
    redis_status = check_redis_status(settings.redis_url)
    ollama_status = await check_ollama_status(settings.ollama_url)
    
    settings.setup_completed = True
    settings.setup_completed_at = datetime.utcnow()
    session.add(settings)
    session.commit()
    
    return {
        "status": "completed",
        "checks": {
            "comfyui": comfyui_status,
            "redis": redis_status,
            "ollama": ollama_status,
        },
        "models_detected": detection_result,
        "storage_root": settings.storage_root_path,
    }


@router.get("/settings")
async def get_settings(session: DbSession):
    """Get current system settings."""
    settings = get_system_settings(session)
    return {
        "storage_root_path": settings.storage_root_path,
        "comfyui_url": settings.comfyui_url,
        "redis_url": settings.redis_url,
        "ollama_url": settings.ollama_url,
        "comfyui_models_path": settings.comfyui_models_path,
        "renderer_target": settings.renderer_target_default.value,
        "cleanup_policy": settings.cleanup_policy.value,
        "setup_completed": settings.setup_completed,
    }


@router.patch("/settings")
async def update_settings(
    request: SetupRequest,
    session: DbSession,
):
    """Update system settings."""
    settings = get_system_settings(session)
    
    if request.storage_root_path:
        settings.storage_root_path = request.storage_root_path
    if request.comfyui_url:
        settings.comfyui_url = request.comfyui_url
    if request.redis_url:
        settings.redis_url = request.redis_url
    if request.ollama_url:
        settings.ollama_url = request.ollama_url
    if request.comfyui_models_path:
        settings.comfyui_models_path = request.comfyui_models_path
    
    session.add(settings)
    session.commit()
    
    return {"status": "updated"}


# ============================================================================
# Renderer Target
# ============================================================================

@router.patch("/renderer")
async def set_renderer_target(
    request: RendererRequest,
    session: DbSession,
):
    """Set default renderer target."""
    settings = get_system_settings(session)
    
    settings.renderer_target_default = RendererTarget(request.default_target)
    if request.remote_worker_url:
        settings.remote_worker_url = request.remote_worker_url
    
    session.add(settings)
    session.commit()
    
    return {
        "status": "updated",
        "renderer_target": settings.renderer_target_default.value,
    }
