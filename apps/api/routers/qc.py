"""
QC Router

API endpoints for quality control checks.
"""
from uuid import UUID
from pydantic import BaseModel
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models import Run, Project, Shot, Asset, QCStatus
from services.qc import run_keyframe_qc, run_clip_qc

router = APIRouter(tags=["qc"])


class QCRunRequest(BaseModel):
    """Request to run QC."""
    blur_threshold: float = 100.0
    check_face: bool = False


class QCStatusResponse(BaseModel):
    """QC status response."""
    total_shots: int
    passed: int
    warned: int
    failed: int
    not_run: int


@router.post("/runs/{run_id}/qc/keyframes/run")
async def run_keyframes_qc(
    run_id: UUID,
    request: QCRunRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """Run QC on all keyframes in a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get aspect ratio from project
    target_ratio = project.aspect_ratio
    
    # Get all shots with keyframes
    shots = session.exec(
        select(Shot).where(Shot.run_id == run_id)
    ).all()
    
    results = []
    
    for shot in shots:
        if not shot.keyframe_asset_id:
            continue
        
        asset = session.get(Asset, shot.keyframe_asset_id)
        if not asset:
            continue
        
        # Run QC
        qc_result = run_keyframe_qc(
            image_path=asset.file_path,
            target_ratio=target_ratio,
            blur_threshold=request.blur_threshold,
            check_face=request.check_face or run.qc_face_required,
        )
        
        # Update shot
        if qc_result.passed:
            shot.qc_status = QCStatus.PASS
        elif qc_result.errors:
            shot.qc_status = QCStatus.FAIL
        else:
            shot.qc_status = QCStatus.WARN
        
        shot.qc_warnings_json = {
            "warnings": qc_result.warnings,
            "errors": qc_result.errors,
            "scores": qc_result.scores,
            "auto_regen": qc_result.auto_regen_suggested,
        }
        
        session.add(shot)
        
        results.append({
            "shot_id": str(shot.id),
            "order_index": shot.order_index,
            "qc_status": shot.qc_status.value,
            "warnings": qc_result.warnings,
            "errors": qc_result.errors,
            "auto_regen_suggested": qc_result.auto_regen_suggested,
        })
    
    session.commit()
    
    return {
        "status": "completed",
        "shots_checked": len(results),
        "results": results,
    }


@router.post("/runs/{run_id}/qc/clips/run")
async def run_clips_qc(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Run QC on all video clips in a run."""
    from models import VideoClip, ClipType, VideoClipStatus
    
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get shots for duration info
    shots = session.exec(select(Shot).where(Shot.run_id == run_id)).all()
    shot_durations = {str(s.id): s.duration_sec for s in shots}
    
    # Get all clips
    clips = session.exec(
        select(VideoClip).where(
            VideoClip.run_id == run_id,
            VideoClip.status == VideoClipStatus.SUCCEEDED,
        )
    ).all()
    
    results = []
    
    for clip in clips:
        target_duration = shot_durations.get(str(clip.shot_id), 4)
        
        qc_result = run_clip_qc(
            clip_path=clip.file_path,
            target_duration=target_duration,
            target_fps=30,
        )
        
        results.append({
            "clip_id": str(clip.id),
            "shot_id": str(clip.shot_id) if clip.shot_id else None,
            "passed": qc_result.passed,
            "warnings": qc_result.warnings,
            "errors": qc_result.errors,
        })
    
    return {
        "status": "completed",
        "clips_checked": len(results),
        "results": results,
    }


@router.get("/runs/{run_id}/qc/status", response_model=QCStatusResponse)
async def get_qc_status(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get QC status summary for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    shots = session.exec(select(Shot).where(Shot.run_id == run_id)).all()
    
    passed = sum(1 for s in shots if s.qc_status == QCStatus.PASS)
    warned = sum(1 for s in shots if s.qc_status == QCStatus.WARN)
    failed = sum(1 for s in shots if s.qc_status == QCStatus.FAIL)
    not_run = sum(1 for s in shots if s.qc_status == QCStatus.NOT_RUN)
    
    return QCStatusResponse(
        total_shots=len(shots),
        passed=passed,
        warned=warned,
        failed=failed,
        not_run=not_run,
    )


@router.get("/runs/{run_id}/shots/{shot_id}/qc")
async def get_shot_qc(
    run_id: UUID,
    shot_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get QC details for a specific shot."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    shot = session.get(Shot, shot_id)
    if not shot or shot.run_id != run_id:
        raise HTTPException(status_code=404, detail="Shot not found")
    
    return {
        "shot_id": str(shot.id),
        "qc_status": shot.qc_status.value,
        "qc_details": shot.qc_warnings_json,
    }
