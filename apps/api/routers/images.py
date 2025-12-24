"""
Images Router

API endpoints for image generation (hero frames and keyframes).
"""
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models import Run, RunStatus, Project, Shot, Asset, AssetRole, ImageGenerationJob, ImageJobStatus
from models.shot import KeyframeStatus
from services.queue import (
    enqueue_hero_frames_job,
    enqueue_keyframe_job,
    enqueue_keyframes_all_job,
    enqueue_regenerate_keyframe_job,
)

router = APIRouter(tags=["images"])


# ============================================================================
# Request/Response Models
# ============================================================================

class HeroGenerateRequest(BaseModel):
    """Request to generate hero frames."""
    width: int = Field(default=768, ge=256, le=2048)
    height: int = Field(default=1344, ge=256, le=2048)
    steps: int = Field(default=6, ge=1, le=50)
    cfg: float = Field(default=3.5, ge=1, le=20)
    checkpoint: Optional[str] = None


class KeyframesGenerateRequest(BaseModel):
    """Request to generate keyframes."""
    width: int = Field(default=768, ge=256, le=2048)
    height: int = Field(default=1344, ge=256, le=2048)
    steps: int = Field(default=6, ge=1, le=50)
    cfg: float = Field(default=3.5, ge=1, le=20)
    use_ip_adapter: bool = False
    reference_strategy: str = "hero_only"
    checkpoint: Optional[str] = None


class KeyframeRegenerateRequest(BaseModel):
    """Request to regenerate a keyframe."""
    seed_mode: str = Field(default="new", pattern="^(same|new)$")
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None


class HeroAssetsResponse(BaseModel):
    """Response with hero frame assets."""
    style_master: Optional[dict] = None
    character_anchor: Optional[dict] = None


class ImageStatusResponse(BaseModel):
    """Response with overall image generation status."""
    hero_status: str
    keyframes_total: int
    keyframes_generated: int
    keyframes_failed: int
    keyframes_running: int


# ============================================================================
# Hero Frame Endpoints
# ============================================================================

@router.post("/runs/{run_id}/images/hero/start")
async def start_hero_generation(
    run_id: UUID,
    request: HeroGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start hero frame generation (style master + character anchor)."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    if run.status not in [RunStatus.PLANNED, RunStatus.APPROVED]:
        raise HTTPException(status_code=400, detail=f"Run must be PLANNED or APPROVED, got {run.status}")
    
    params = request.model_dump(exclude_none=True)
    job_id = enqueue_hero_frames_job(run.id, project.id, params)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": "Hero frame generation started",
    }


@router.get("/runs/{run_id}/images/hero", response_model=HeroAssetsResponse)
async def get_hero_assets(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get hero frame assets for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Find hero assets
    style_statement = select(Asset).where(
        Asset.run_id == run_id,
        Asset.role == AssetRole.HERO_FRAME_STYLE,
    ).order_by(Asset.created_at.desc())
    style_asset = session.exec(style_statement).first()
    
    char_statement = select(Asset).where(
        Asset.run_id == run_id,
        Asset.role == AssetRole.HERO_FRAME_CHARACTER,
    ).order_by(Asset.created_at.desc())
    char_asset = session.exec(char_statement).first()
    
    return HeroAssetsResponse(
        style_master={
            "id": str(style_asset.id),
            "file_path": style_asset.file_path,
            "seed": style_asset.seed,
        } if style_asset else None,
        character_anchor={
            "id": str(char_asset.id),
            "file_path": char_asset.file_path,
            "seed": char_asset.seed,
        } if char_asset else None,
    )


# ============================================================================
# Keyframe Endpoints
# ============================================================================

@router.post("/runs/{run_id}/images/keyframes/start")
async def start_keyframes_generation(
    run_id: UUID,
    request: KeyframesGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start keyframe generation for all shots."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    params = request.model_dump(exclude_none=True)
    job_id = enqueue_keyframes_all_job(run.id, project.id, params)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": "Keyframe generation started for all shots",
    }


@router.post("/runs/{run_id}/shots/{shot_id}/keyframe/start")
async def start_single_keyframe(
    run_id: UUID,
    shot_id: str,
    request: KeyframesGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start keyframe generation for a single shot."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    # Verify shot exists
    shots = run.director_json.get("shots", [])
    if not any(s.get("shot_id") == shot_id for s in shots):
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    
    params = request.model_dump(exclude_none=True)
    job_id = enqueue_keyframe_job(run.id, project.id, shot_id, params)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Keyframe generation started for {shot_id}",
    }


@router.post("/runs/{run_id}/shots/{shot_id}/keyframe/regenerate")
async def regenerate_keyframe(
    run_id: UUID,
    shot_id: str,
    request: KeyframeRegenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Regenerate a keyframe with options."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Find the shot in DB
    statement = select(Shot).where(Shot.run_id == run_id)
    db_shots = session.exec(statement).all()
    
    # Check if shot is approved (locked)
    shots = run.director_json.get("shots", [])
    shot_index = next((i for i, s in enumerate(shots) if s.get("shot_id") == shot_id), None)
    
    if shot_index is not None and shot_index < len(db_shots):
        db_shot = db_shots[shot_index]
        if db_shot.keyframe_status == KeyframeStatus.APPROVED:
            raise HTTPException(status_code=400, detail="Cannot regenerate approved keyframe. Unlock it first.")
    
    params = {}
    if request.width:
        params["width"] = request.width
    if request.height:
        params["height"] = request.height
    if request.steps:
        params["steps"] = request.steps
    if request.cfg:
        params["cfg"] = request.cfg
    
    job_id = enqueue_regenerate_keyframe_job(
        run.id, project.id, shot_id, request.seed_mode, params if params else None
    )
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Keyframe regeneration started for {shot_id}",
    }


# ============================================================================
# Status Endpoints
# ============================================================================

@router.get("/runs/{run_id}/images/status", response_model=ImageStatusResponse)
async def get_images_status(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get overall image generation status for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check hero status
    hero_jobs = session.exec(
        select(ImageGenerationJob).where(
            ImageGenerationJob.run_id == run_id,
            ImageGenerationJob.job_type.in_(["hero_style", "hero_character"]),
        )
    ).all()
    
    hero_succeeded = sum(1 for j in hero_jobs if j.status == ImageJobStatus.SUCCEEDED)
    hero_status = "complete" if hero_succeeded == 2 else "incomplete"
    
    # Check keyframes
    shots = run.director_json.get("shots", []) if run.director_json else []
    total_shots = len(shots)
    
    db_shots = session.exec(select(Shot).where(Shot.run_id == run_id)).all()
    
    generated = sum(1 for s in db_shots if s.keyframe_status == KeyframeStatus.GENERATED)
    approved = sum(1 for s in db_shots if s.keyframe_status == KeyframeStatus.APPROVED)
    failed = sum(1 for s in db_shots if s.keyframe_status == KeyframeStatus.FAILED)
    running = sum(1 for s in db_shots if s.keyframe_status in [KeyframeStatus.QUEUED, KeyframeStatus.RUNNING])
    
    return ImageStatusResponse(
        hero_status=hero_status,
        keyframes_total=total_shots,
        keyframes_generated=generated + approved,
        keyframes_failed=failed,
        keyframes_running=running,
    )


@router.post("/runs/{run_id}/shots/{shot_id}/keyframe/approve")
async def approve_keyframe(
    run_id: UUID,
    shot_id: str,
    session: DbSession,
    current_user: CurrentUser,
):
    """Approve and lock a keyframe."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Find shot by index from director_json
    shots = run.director_json.get("shots", []) if run.director_json else []
    shot_index = next((i for i, s in enumerate(shots) if s.get("shot_id") == shot_id), None)
    
    if shot_index is None:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    
    # Find DB shot
    statement = select(Shot).where(
        Shot.run_id == run_id,
        Shot.order_index == shot_index,
    )
    db_shot = session.exec(statement).first()
    
    if not db_shot:
        raise HTTPException(status_code=404, detail=f"Shot record not found")
    
    if db_shot.keyframe_status != KeyframeStatus.GENERATED:
        raise HTTPException(status_code=400, detail="Keyframe must be generated before approval")
    
    db_shot.keyframe_status = KeyframeStatus.APPROVED
    session.add(db_shot)
    session.commit()
    
    return {"status": "approved", "shot_id": shot_id}


@router.post("/runs/{run_id}/shots/{shot_id}/keyframe/unlock")
async def unlock_keyframe(
    run_id: UUID,
    shot_id: str,
    session: DbSession,
    current_user: CurrentUser,
):
    """Unlock an approved keyframe."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    shots = run.director_json.get("shots", []) if run.director_json else []
    shot_index = next((i for i, s in enumerate(shots) if s.get("shot_id") == shot_id), None)
    
    if shot_index is None:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    
    statement = select(Shot).where(
        Shot.run_id == run_id,
        Shot.order_index == shot_index,
    )
    db_shot = session.exec(statement).first()
    
    if not db_shot:
        raise HTTPException(status_code=404, detail=f"Shot record not found")
    
    db_shot.keyframe_status = KeyframeStatus.GENERATED
    session.add(db_shot)
    session.commit()
    
    return {"status": "unlocked", "shot_id": shot_id}


# ============================================================================
# Variants Endpoints (Phase 5)
# ============================================================================

class VariantsGenerateRequest(BaseModel):
    """Request to generate variants."""
    count: int = Field(default=3, ge=1, le=5)
    seed_mode: str = Field(default="offset", pattern="^(offset|random)$")
    reference_strategy: str = Field(default="hero_plus_prev")


class VariantSelectRequest(BaseModel):
    """Request to select a variant."""
    asset_id: UUID


@router.post("/runs/{run_id}/shots/{shot_id}/keyframe/variants/start")
async def start_variants_generation(
    run_id: UUID,
    shot_id: str,
    request: VariantsGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Generate multiple keyframe variants for a shot."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    # Verify shot exists
    shots = run.director_json.get("shots", [])
    if not any(s.get("shot_id") == shot_id for s in shots):
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    
    # Update shot variant count
    shot_index = next((i for i, s in enumerate(shots) if s.get("shot_id") == shot_id), None)
    if shot_index is not None:
        db_shot = session.exec(
            select(Shot).where(Shot.run_id == run_id, Shot.order_index == shot_index)
        ).first()
        if db_shot:
            db_shot.variant_count = request.count
            session.add(db_shot)
            session.commit()
    
    # Enqueue variant generation jobs
    from services.queue import enqueue_variants_job
    job_id = enqueue_variants_job(
        run.id, project.id, shot_id,
        request.count, request.seed_mode, request.reference_strategy
    )
    
    return {
        "status": "queued",
        "job_id": job_id,
        "variant_count": request.count,
        "message": f"Generating {request.count} variants for {shot_id}",
    }


@router.post("/runs/{run_id}/shots/{shot_id}/keyframe/variants/select")
async def select_variant(
    run_id: UUID,
    shot_id: str,
    request: VariantSelectRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Select a variant as the approved keyframe."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify asset exists and belongs to this shot
    asset = session.get(Asset, request.asset_id)
    if not asset or asset.run_id != run_id:
        raise HTTPException(status_code=404, detail="Variant asset not found")
    
    if asset.role != AssetRole.KEYFRAME_VARIANT:
        raise HTTPException(status_code=400, detail="Asset is not a keyframe variant")
    
    # Find shot
    shots = run.director_json.get("shots", []) if run.director_json else []
    shot_index = next((i for i, s in enumerate(shots) if s.get("shot_id") == shot_id), None)
    
    if shot_index is None:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    
    db_shot = session.exec(
        select(Shot).where(Shot.run_id == run_id, Shot.order_index == shot_index)
    ).first()
    
    if not db_shot:
        raise HTTPException(status_code=404, detail="Shot record not found")
    
    # Update shot with selected variant
    db_shot.selected_variant_asset_id = asset.id
    db_shot.keyframe_asset_id = asset.id
    db_shot.keyframe_status = KeyframeStatus.APPROVED
    db_shot.keyframe_seed = asset.seed
    
    session.add(db_shot)
    session.commit()
    
    return {
        "status": "selected",
        "shot_id": shot_id,
        "asset_id": str(asset.id),
    }


@router.get("/runs/{run_id}/shots/{shot_id}/keyframe/variants")
async def list_variants(
    run_id: UUID,
    shot_id: str,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all variants for a shot."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Find shot
    shots = run.director_json.get("shots", []) if run.director_json else []
    shot_index = next((i for i, s in enumerate(shots) if s.get("shot_id") == shot_id), None)
    
    if shot_index is None:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    
    db_shot = session.exec(
        select(Shot).where(Shot.run_id == run_id, Shot.order_index == shot_index)
    ).first()
    
    # Get variant assets
    variants = session.exec(
        select(Asset).where(
            Asset.run_id == run_id,
            Asset.shot_id == db_shot.id if db_shot else None,
            Asset.role == AssetRole.KEYFRAME_VARIANT,
        ).order_by(Asset.variant_index)
    ).all()
    
    return {
        "shot_id": shot_id,
        "variant_count": len(variants),
        "selected_variant_id": str(db_shot.selected_variant_asset_id) if db_shot and db_shot.selected_variant_asset_id else None,
        "variants": [
            {
                "id": str(v.id),
                "variant_index": v.variant_index,
                "file_path": v.file_path,
                "seed": v.seed,
            }
            for v in variants
        ],
    }

