"""
Models Router

API endpoints for model management.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from dependencies import DbSession
from models.system_model import Model, ModelType, ModelStatus
from services.model_manager import (
    list_models, get_model, verify_model, locate_model,
    get_missing_models, auto_detect_models, seed_required_models,
    get_system_settings,
)

router = APIRouter(prefix="/models", tags=["models"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ModelResponse(BaseModel):
    """Model information response."""
    id: str
    name: str
    type: str
    status: str
    local_path: Optional[str]
    size_bytes: Optional[int]
    required_for: Optional[str]
    notes: Optional[str]


class LocateRequest(BaseModel):
    """Request to locate a model."""
    local_path: str


class InstallRequest(BaseModel):
    """Request to install a model."""
    source_url: Optional[str] = None
    huggingface_repo: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("")
async def list_all_models(
    session: DbSession,
    type_filter: Optional[str] = None,
):
    """List all registered models."""
    # Ensure models are seeded
    seed_required_models(session)
    
    type_enum = ModelType(type_filter) if type_filter else None
    models = list_models(session, type_enum)
    
    return [
        ModelResponse(
            id=str(m.id),
            name=m.name,
            type=m.type.value,
            status=m.status.value,
            local_path=m.local_path,
            size_bytes=m.size_bytes,
            required_for=m.required_for,
            notes=m.notes,
        )
        for m in models
    ]


@router.get("/missing")
async def list_missing_models(session: DbSession):
    """List models that are not installed."""
    seed_required_models(session)
    models = get_missing_models(session)
    
    return [
        ModelResponse(
            id=str(m.id),
            name=m.name,
            type=m.type.value,
            status=m.status.value,
            local_path=m.local_path,
            size_bytes=m.size_bytes,
            required_for=m.required_for,
            notes=m.notes,
        )
        for m in models
    ]


@router.get("/{model_id}")
async def get_model_details(
    model_id: UUID,
    session: DbSession,
):
    """Get details of a specific model."""
    model = get_model(session, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    return ModelResponse(
        id=str(model.id),
        name=model.name,
        type=model.type.value,
        status=model.status.value,
        local_path=model.local_path,
        size_bytes=model.size_bytes,
        required_for=model.required_for,
        notes=model.notes,
    )


@router.post("/{model_id}/verify")
async def verify_model_endpoint(
    model_id: UUID,
    session: DbSession,
):
    """Verify a model exists and is valid."""
    result = verify_model(session, model_id)
    return result


@router.post("/{model_id}/locate")
async def locate_model_endpoint(
    model_id: UUID,
    request: LocateRequest,
    session: DbSession,
):
    """Set the local path for a model."""
    result = locate_model(session, model_id, request.local_path)
    return result


@router.post("/auto-detect")
async def auto_detect_models_endpoint(session: DbSession):
    """Auto-detect models in ComfyUI models directory."""
    settings = get_system_settings(session)
    
    if not settings.comfyui_models_path:
        raise HTTPException(
            status_code=400, 
            detail="ComfyUI models path not configured"
        )
    
    result = auto_detect_models(session, settings.comfyui_models_path)
    return result


@router.post("/install")
async def install_model(
    request: InstallRequest,
    session: DbSession,
):
    """Install a model (placeholder for download implementation)."""
    # TODO: Implement actual download from source_url or huggingface
    return {
        "status": "not_implemented",
        "message": "Model download not yet implemented. Please manually download and use /locate.",
    }


@router.delete("/{model_id}")
async def remove_model(
    model_id: UUID,
    session: DbSession,
):
    """Remove a model from registry (does not delete file)."""
    model = get_model(session, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model.status = ModelStatus.NOT_INSTALLED
    model.local_path = None
    session.add(model)
    session.commit()
    
    return {"status": "removed", "model_id": str(model_id)}
