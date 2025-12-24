"""
Performance Router

API endpoints for performance benchmarking and profiles.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from dependencies import DbSession
from models.system_model import PerformanceProfile
from services.benchmark import (
    run_full_benchmark, run_image_benchmark, run_video_benchmark,
    get_machine_info, get_active_profile, apply_profile_defaults,
)

router = APIRouter(prefix="/performance", tags=["performance"])


# ============================================================================
# Response Models
# ============================================================================

class ProfileResponse(BaseModel):
    """Performance profile response."""
    id: str
    machine_name: str
    machine_chip: str | None
    machine_ram_gb: int | None
    tested_at: str
    image_test_seconds: float | None
    preview_video_test_seconds: float | None
    final_video_test_seconds: float | None
    safe_defaults: dict
    is_active: bool


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/machine")
async def get_machine():
    """Get current machine information."""
    return get_machine_info()


@router.post("/benchmark")
async def run_benchmark(session: DbSession):
    """Run full performance benchmark."""
    try:
        profile = run_full_benchmark(session)
        
        return ProfileResponse(
            id=str(profile.id),
            machine_name=profile.machine_name,
            machine_chip=profile.machine_chip,
            machine_ram_gb=profile.machine_ram_gb,
            tested_at=profile.tested_at.isoformat(),
            image_test_seconds=profile.image_test_seconds,
            preview_video_test_seconds=profile.preview_video_test_seconds,
            final_video_test_seconds=profile.final_video_test_seconds,
            safe_defaults=profile.safe_defaults_json,
            is_active=profile.is_active,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/benchmark/image")
async def run_image_benchmark_endpoint():
    """Run image-only benchmark."""
    result = run_image_benchmark()
    return result


@router.post("/benchmark/video/preview")
async def run_preview_video_benchmark():
    """Run preview video benchmark."""
    result = run_video_benchmark(duration_sec=2.0, clip_type="preview")
    return result


@router.post("/benchmark/video/final")
async def run_final_video_benchmark():
    """Run final video benchmark."""
    result = run_video_benchmark(duration_sec=4.0, clip_type="final")
    return result


@router.get("/profile")
async def get_current_profile(session: DbSession):
    """Get the currently active performance profile."""
    profile = get_active_profile(session)
    
    if not profile:
        return {"active": False, "message": "No performance profile. Run /benchmark first."}
    
    return ProfileResponse(
        id=str(profile.id),
        machine_name=profile.machine_name,
        machine_chip=profile.machine_chip,
        machine_ram_gb=profile.machine_ram_gb,
        tested_at=profile.tested_at.isoformat(),
        image_test_seconds=profile.image_test_seconds,
        preview_video_test_seconds=profile.preview_video_test_seconds,
        final_video_test_seconds=profile.final_video_test_seconds,
        safe_defaults=profile.safe_defaults_json,
        is_active=profile.is_active,
    )


@router.get("/profiles")
async def list_profiles(session: DbSession):
    """List all performance profiles."""
    profiles = list(session.exec(select(PerformanceProfile)).all())
    
    return [
        ProfileResponse(
            id=str(p.id),
            machine_name=p.machine_name,
            machine_chip=p.machine_chip,
            machine_ram_gb=p.machine_ram_gb,
            tested_at=p.tested_at.isoformat(),
            image_test_seconds=p.image_test_seconds,
            preview_video_test_seconds=p.preview_video_test_seconds,
            final_video_test_seconds=p.final_video_test_seconds,
            safe_defaults=p.safe_defaults_json,
            is_active=p.is_active,
        )
        for p in profiles
    ]


@router.patch("/profile/select/{profile_id}")
async def select_profile(profile_id: UUID, session: DbSession):
    """Select and apply a performance profile."""
    result = apply_profile_defaults(session, profile_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    
    return result
