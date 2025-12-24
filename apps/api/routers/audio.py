"""
Audio Router

API endpoints for voiceover and music.
"""
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models import Run, Project, AudioTrack, TrackType
from services.queue import enqueue_voiceover_job
from services.audio import build_voiceover_script, get_music_library

router = APIRouter(tags=["audio"])


# ============================================================================
# Request/Response Models
# ============================================================================

class VoiceoverRequest(BaseModel):
    """Request to generate voiceover."""
    script: Optional[str] = None
    voice_id: str = "default"


class MusicUploadRequest(BaseModel):
    """Request to set music track."""
    music_id: Optional[str] = None
    music_name: Optional[str] = None
    volume: float = Field(default=0.3, ge=0, le=2)


class AudioStatusResponse(BaseModel):
    """Response with audio status."""
    has_voiceover: bool
    has_music: bool
    voiceover_duration: Optional[float]
    music_duration: Optional[float]


# ============================================================================
# Voiceover Endpoints
# ============================================================================

@router.post("/runs/{run_id}/audio/voiceover/generate")
async def generate_voiceover(
    run_id: UUID,
    request: VoiceoverRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Generate voiceover from script."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    # Use provided script or auto-generate
    script = request.script
    if not script:
        script = build_voiceover_script(run.director_json)
    
    job_id = enqueue_voiceover_job(run.id, project.id, script)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": "Voiceover generation started",
        "script_preview": script[:200] if script else None,
    }


@router.get("/runs/{run_id}/audio/voiceover/script")
async def get_voiceover_script(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get auto-generated voiceover script."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not run.director_json:
        raise HTTPException(status_code=400, detail="No plan generated yet")
    
    script = build_voiceover_script(run.director_json)
    
    # Estimate duration
    word_count = len(script.split())
    duration_estimate = max(5.0, word_count / 2.5)
    
    return {
        "script": script,
        "word_count": word_count,
        "duration_estimate_sec": duration_estimate,
    }


# ============================================================================
# Music Endpoints
# ============================================================================

@router.get("/runs/{run_id}/audio/music/library")
async def list_music_library(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List available music tracks."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return get_music_library()


@router.post("/runs/{run_id}/audio/music/set")
async def set_music_track(
    run_id: UUID,
    request: MusicUploadRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Set music track for the run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # For now, just record the selection
    # In production, this would link to actual music files
    from services.audio import get_audio_dir
    audio_dir = get_audio_dir(project.id, run_id)
    
    # Create placeholder audio track record
    music_track = AudioTrack(
        run_id=run_id,
        track_type=TrackType.MUSIC,
        file_path=str(audio_dir / "music.mp3"),
        duration_sec=60.0,
        music_name=request.music_name or request.music_id,
        volume_level=request.volume,
    )
    session.add(music_track)
    session.commit()
    
    return {
        "status": "set",
        "music_name": request.music_name or request.music_id,
        "volume": request.volume,
    }


# ============================================================================
# Status Endpoints
# ============================================================================

@router.get("/runs/{run_id}/audio/status", response_model=AudioStatusResponse)
async def get_audio_status(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get audio status for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get audio tracks
    tracks = session.exec(select(AudioTrack).where(AudioTrack.run_id == run_id)).all()
    
    voiceover = next((t for t in tracks if t.track_type == TrackType.VOICEOVER), None)
    music = next((t for t in tracks if t.track_type == TrackType.MUSIC), None)
    
    return AudioStatusResponse(
        has_voiceover=voiceover is not None,
        has_music=music is not None,
        voiceover_duration=voiceover.duration_sec if voiceover else None,
        music_duration=music.duration_sec if music else None,
    )


@router.get("/runs/{run_id}/audio/tracks")
async def list_audio_tracks(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all audio tracks for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    tracks = session.exec(select(AudioTrack).where(AudioTrack.run_id == run_id)).all()
    
    return [
        {
            "id": str(t.id),
            "track_type": t.track_type.value,
            "file_path": t.file_path,
            "duration_sec": t.duration_sec,
            "script_text": t.script_text[:100] if t.script_text else None,
            "music_name": t.music_name,
        }
        for t in tracks
    ]
