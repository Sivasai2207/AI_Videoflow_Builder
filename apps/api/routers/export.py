"""
Export Router

API endpoints for video export and download.
"""
from pathlib import Path
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models import Run, Project, FinalExport, ExportPreset, ExportStatus
from services.queue import enqueue_export_job

router = APIRouter(tags=["export"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ExportRequest(BaseModel):
    """Request to export video."""
    preset: str = Field(default="instagram_reels", pattern="^(instagram_reels|youtube_shorts|tiktok|youtube|custom)$")


class ExportStatusResponse(BaseModel):
    """Response with export status."""
    id: str
    preset: str
    status: str
    file_path: Optional[str]
    file_size_bytes: Optional[int]


# ============================================================================
# Export Endpoints
# ============================================================================

@router.post("/runs/{run_id}/export/start")
async def start_export(
    run_id: UUID,
    request: ExportRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start video export with platform preset."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    job_id = enqueue_export_job(run.id, project.id, request.preset)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "preset": request.preset,
        "message": f"Export started for {request.preset}",
    }


@router.get("/runs/{run_id}/export/status")
async def get_export_status(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get export status for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    exports = session.exec(
        select(FinalExport).where(FinalExport.run_id == run_id).order_by(FinalExport.created_at.desc())
    ).all()
    
    return [
        {
            "id": str(e.id),
            "preset": e.preset.value,
            "status": e.status.value,
            "file_path": e.file_path,
            "file_size_bytes": e.file_size_bytes,
            "width": e.width,
            "height": e.height,
            "created_at": e.created_at.isoformat(),
        }
        for e in exports
    ]


@router.get("/runs/{run_id}/export/{export_id}/download")
async def download_export(
    run_id: UUID,
    export_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Download exported video."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    export = session.get(FinalExport, export_id)
    if not export or export.run_id != run_id:
        raise HTTPException(status_code=404, detail="Export not found")
    
    if export.status != ExportStatus.SUCCEEDED:
        raise HTTPException(status_code=400, detail=f"Export not ready: {export.status.value}")
    
    if not export.file_path or not Path(export.file_path).exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    
    filename = f"video_{export.preset.value}.mp4"
    
    return FileResponse(
        path=export.file_path,
        media_type="video/mp4",
        filename=filename,
    )


@router.get("/runs/{run_id}/export/presets")
async def list_export_presets(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List available export presets."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return [
        {
            "id": "instagram_reels",
            "name": "Instagram Reels",
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16",
            "max_duration_sec": 90,
            "bitrate": "8 Mbps",
        },
        {
            "id": "youtube_shorts",
            "name": "YouTube Shorts",
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16",
            "max_duration_sec": 60,
            "bitrate": "10 Mbps",
        },
        {
            "id": "tiktok",
            "name": "TikTok",
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16",
            "max_duration_sec": 180,
            "bitrate": "8 Mbps",
        },
        {
            "id": "youtube",
            "name": "YouTube",
            "width": 1920,
            "height": 1080,
            "aspect_ratio": "16:9",
            "max_duration_sec": None,
            "bitrate": "12 Mbps",
        },
    ]


# ============================================================================
# Phase 5: Export Settings
# ============================================================================

class ExportSettingsRequest(BaseModel):
    """Request to update export settings."""
    transition: Optional[str] = Field(default=None, pattern="^(hard_cut|fade|dip_to_black)$")
    transition_frames: Optional[int] = Field(default=None, ge=0, le=30)
    quality_profile: Optional[str] = Field(default=None, pattern="^(draft|standard|high)$")


@router.patch("/runs/{run_id}/export/settings")
async def update_export_settings(
    run_id: UUID,
    request: ExportSettingsRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Update export settings for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Update run settings
    from models.run import TransitionType, QualityProfile
    
    if request.transition:
        run.transition_type = TransitionType(request.transition)
    
    if request.transition_frames is not None:
        run.transition_frames = request.transition_frames
    
    if request.quality_profile:
        run.quality_profile = QualityProfile(request.quality_profile)
    
    session.add(run)
    session.commit()
    
    return {
        "status": "updated",
        "transition_type": run.transition_type.value,
        "transition_frames": run.transition_frames,
        "quality_profile": run.quality_profile.value,
    }


@router.get("/runs/{run_id}/export/settings")
async def get_export_settings(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get export settings for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "transition_type": run.transition_type.value,
        "transition_frames": run.transition_frames,
        "quality_profile": run.quality_profile.value,
        "default_reference_strategy": run.default_reference_strategy.value,
        "default_variant_count": run.default_variant_count,
        "qc_blur_check": run.qc_blur_check,
        "qc_face_required": run.qc_face_required,
        "qc_no_text_warning": run.qc_no_text_warning,
    }


@router.get("/runs/{run_id}/export/srt")
async def generate_srt(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Generate SRT subtitle template from voiceover script."""
    from models import AudioTrack, TrackType
    
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get voiceover track
    voiceover = session.exec(
        select(AudioTrack).where(
            AudioTrack.run_id == run_id,
            AudioTrack.track_type == TrackType.VOICEOVER,
        )
    ).first()
    
    if not voiceover or not voiceover.script_text:
        # Generate from Director JSON
        if run.director_json:
            shots = run.director_json.get("shots", [])
            srt_lines = []
            current_time = 0.0
            
            for i, shot in enumerate(shots):
                duration = shot.get("duration_sec", 4)
                voiceover_text = shot.get("audio", {}).get("voiceover_text", "")
                
                if voiceover_text:
                    start_ms = int(current_time * 1000)
                    end_ms = int((current_time + duration) * 1000)
                    
                    start_str = f"{start_ms // 3600000:02d}:{(start_ms // 60000) % 60:02d}:{(start_ms // 1000) % 60:02d},{start_ms % 1000:03d}"
                    end_str = f"{end_ms // 3600000:02d}:{(end_ms // 60000) % 60:02d}:{(end_ms // 1000) % 60:02d},{end_ms % 1000:03d}"
                    
                    srt_lines.append(f"{i + 1}")
                    srt_lines.append(f"{start_str} --> {end_str}")
                    srt_lines.append(voiceover_text)
                    srt_lines.append("")
                
                current_time += duration
            
            srt_content = "\n".join(srt_lines)
        else:
            srt_content = "1\n00:00:00,000 --> 00:00:05,000\n[No script available]\n"
    else:
        # Use voiceover script
        script = voiceover.script_text
        duration = voiceover.duration_sec or 30
        
        srt_content = f"1\n00:00:00,000 --> 00:00:{int(duration):02d},000\n{script}\n"
    
    return {
        "srt": srt_content,
        "format": "srt",
    }

