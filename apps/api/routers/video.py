"""
Video Router

API endpoints for video generation and stitching.
"""
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models import Run, RunStatus, Project, VideoClip, ClipType, VideoClipStatus
from services.queue import (
    enqueue_shot_video_job,
    enqueue_all_videos_job,
    enqueue_stitch_job,
    enqueue_final_video_job,
)

router = APIRouter(tags=["video"])


# ============================================================================
# Request/Response Models
# ============================================================================

class VideoGenerateRequest(BaseModel):
    """Request to generate video."""
    clip_type: str = Field(default="preview", pattern="^(preview|final)$")


class VideoStatusResponse(BaseModel):
    """Response with video generation status."""
    total_shots: int
    videos_generated: int
    videos_running: int
    videos_failed: int
    stitched: bool
    has_final: bool


class StitchRequest(BaseModel):
    """Request to stitch videos."""
    include_voiceover: bool = True
    include_music: bool = False


# ============================================================================
# Video Generation Endpoints
# ============================================================================

@router.post("/runs/{run_id}/video/shots/{shot_id}/start")
async def start_shot_video(
    run_id: UUID,
    shot_id: str,
    request: VideoGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start video generation for a single shot."""
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
    
    job_id = enqueue_shot_video_job(run.id, project.id, shot_id, request.clip_type)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Video generation started for {shot_id}",
    }


@router.post("/runs/{run_id}/video/all/start")
async def start_all_videos(
    run_id: UUID,
    request: VideoGenerateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start video generation for all shots."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    job_id = enqueue_all_videos_job(run.id, project.id, request.clip_type)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": "Video generation started for all shots",
    }


@router.post("/runs/{run_id}/video/stitch")
async def stitch_videos(
    run_id: UUID,
    request: StitchRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Stitch all shot videos into final video."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # First stitch
    stitch_job_id = enqueue_stitch_job(run.id, project.id)
    
    # Then add audio if requested
    if request.include_voiceover or request.include_music:
        final_job_id = enqueue_final_video_job(
            run.id, project.id, 
            request.include_voiceover, 
            request.include_music
        )
    else:
        final_job_id = None
    
    return {
        "status": "queued",
        "stitch_job_id": stitch_job_id,
        "final_job_id": final_job_id,
        "message": "Video stitching started",
    }


@router.get("/runs/{run_id}/video/status", response_model=VideoStatusResponse)
async def get_video_status(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get video generation status for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    total_shots = len(run.director_json.get("shots", [])) if run.director_json else 0
    
    # Get video clips
    clips = session.exec(select(VideoClip).where(VideoClip.run_id == run_id)).all()
    
    shot_clips = [c for c in clips if c.shot_id and c.clip_type in [ClipType.PREVIEW, ClipType.FINAL]]
    generated = sum(1 for c in shot_clips if c.status == VideoClipStatus.SUCCEEDED)
    running = sum(1 for c in shot_clips if c.status in [VideoClipStatus.QUEUED, VideoClipStatus.RUNNING])
    failed = sum(1 for c in shot_clips if c.status == VideoClipStatus.FAILED)
    
    stitched = any(c.clip_type == ClipType.STITCHED and c.status == VideoClipStatus.SUCCEEDED for c in clips)
    has_final = any(c for c in clips if c.clip_type == ClipType.STITCHED and c.status == VideoClipStatus.SUCCEEDED)
    
    return VideoStatusResponse(
        total_shots=total_shots,
        videos_generated=generated,
        videos_running=running,
        videos_failed=failed,
        stitched=stitched,
        has_final=has_final,
    )


@router.get("/runs/{run_id}/video/clips")
async def list_video_clips(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all video clips for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    clips = session.exec(
        select(VideoClip).where(VideoClip.run_id == run_id).order_by(VideoClip.created_at)
    ).all()
    
    return [
        {
            "id": str(c.id),
            "shot_id": str(c.shot_id) if c.shot_id else None,
            "clip_type": c.clip_type.value,
            "status": c.status.value,
            "file_path": c.file_path,
            "duration_sec": c.duration_sec,
        }
        for c in clips
    ]
