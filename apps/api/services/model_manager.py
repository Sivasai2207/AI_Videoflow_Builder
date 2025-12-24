"""
Model Manager Service

Manages AI model registry, installation, and verification.
"""
import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlmodel import Session, select

from models.system_model import (
    Model, ModelType, ModelStatus, 
    DEFAULT_REQUIRED_MODELS, SystemSettings,
)


def get_system_settings(session: Session) -> SystemSettings:
    """Get or create system settings."""
    settings = session.get(SystemSettings, 1)
    if not settings:
        settings = SystemSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def seed_required_models(session: Session):
    """Seed the database with required model definitions."""
    for model_def in DEFAULT_REQUIRED_MODELS:
        # Check if already exists
        existing = session.exec(
            select(Model).where(Model.name == model_def["name"])
        ).first()
        
        if not existing:
            model = Model(
                name=model_def["name"],
                type=model_def["type"],
                required_for=model_def.get("required_for"),
                huggingface_repo=model_def.get("huggingface_repo"),
                filename=model_def.get("filename"),
                notes=model_def.get("notes"),
                status=ModelStatus.NOT_INSTALLED,
            )
            session.add(model)
    
    session.commit()


def list_models(session: Session, type_filter: Optional[ModelType] = None) -> List[Model]:
    """List all registered models."""
    query = select(Model)
    if type_filter:
        query = query.where(Model.type == type_filter)
    return list(session.exec(query).all())


def get_model(session: Session, model_id: UUID) -> Optional[Model]:
    """Get a model by ID."""
    return session.get(Model, model_id)


def get_models_for_flow(session: Session, flow: str) -> List[Model]:
    """Get models required for a specific flow (image, video, both)."""
    return list(session.exec(
        select(Model).where(
            (Model.required_for == flow) | (Model.required_for == "both")
        )
    ).all())


def verify_model(session: Session, model_id: UUID) -> Dict[str, Any]:
    """Verify a model exists and is valid."""
    model = session.get(Model, model_id)
    if not model:
        return {"success": False, "error": "Model not found"}
    
    if not model.local_path:
        return {"success": False, "error": "No local path set", "status": "not_installed"}
    
    path = Path(model.local_path)
    if not path.exists():
        model.status = ModelStatus.NOT_INSTALLED
        session.add(model)
        session.commit()
        return {"success": False, "error": "File not found", "status": "not_installed"}
    
    # Get file size
    file_size = path.stat().st_size
    model.size_bytes = file_size
    
    # Optional: verify checksum
    if model.sha256:
        actual_hash = compute_file_hash(path)
        if actual_hash != model.sha256:
            model.status = ModelStatus.INVALID
            session.add(model)
            session.commit()
            return {
                "success": False, 
                "error": "Checksum mismatch", 
                "status": "invalid",
                "expected": model.sha256,
                "actual": actual_hash,
            }
    
    model.status = ModelStatus.INSTALLED
    model.last_verified_at = datetime.utcnow()
    session.add(model)
    session.commit()
    
    return {
        "success": True,
        "status": "installed",
        "size_bytes": file_size,
        "path": str(path),
    }


def compute_file_hash(path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def locate_model(session: Session, model_id: UUID, local_path: str) -> Dict[str, Any]:
    """Set the local path for a model and verify it."""
    model = session.get(Model, model_id)
    if not model:
        return {"success": False, "error": "Model not found"}
    
    path = Path(local_path)
    if not path.exists():
        return {"success": False, "error": "Path does not exist"}
    
    model.local_path = str(path)
    session.add(model)
    session.commit()
    
    return verify_model(session, model_id)


def get_missing_models(session: Session) -> List[Model]:
    """Get list of models that are not installed."""
    return list(session.exec(
        select(Model).where(
            (Model.status == ModelStatus.NOT_INSTALLED) |
            (Model.status == ModelStatus.INVALID)
        )
    ).all())


def auto_detect_models(session: Session, comfyui_models_path: str) -> Dict[str, Any]:
    """Auto-detect models in ComfyUI models directory."""
    base_path = Path(comfyui_models_path)
    
    if not base_path.exists():
        return {"success": False, "error": "ComfyUI models path does not exist"}
    
    detected = []
    
    # Common subdirectories
    subdirs = {
        "checkpoints": ModelType.CHECKPOINT,
        "vae": ModelType.VAE,
        "ipadapter": ModelType.IPADAPTER,
        "clip_vision": ModelType.CLIP_VISION,
        "loras": ModelType.LORA,
    }
    
    for subdir, model_type in subdirs.items():
        subdir_path = base_path / subdir
        if subdir_path.exists():
            for file in subdir_path.glob("*.safetensors"):
                detected.append({
                    "path": str(file),
                    "name": file.stem,
                    "type": model_type,
                })
            for file in subdir_path.glob("*.ckpt"):
                detected.append({
                    "path": str(file),
                    "name": file.stem,
                    "type": model_type,
                })
    
    # Try to match with registered models
    models = list_models(session)
    matched = 0
    
    for model in models:
        if model.filename:
            for det in detected:
                if model.filename in det["path"]:
                    model.local_path = det["path"]
                    model.status = ModelStatus.INSTALLED
                    session.add(model)
                    matched += 1
                    break
    
    session.commit()
    
    return {
        "success": True,
        "detected_count": len(detected),
        "matched_count": matched,
        "detected": detected,
    }
