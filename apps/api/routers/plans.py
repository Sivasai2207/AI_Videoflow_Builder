"""
Plans Router

API endpoints for Director plan management.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models import Run, RunStatus, Project, DirectorPlanVersion
from models.plan_version import DirectorPlanVersionRead, PlanStatus
from schemas.director import PlanGenerateRequest, PlanUpdateRequest, validate_director_json
from services import director as director_service
from services.queue import enqueue_director_job

router = APIRouter(tags=["plans"])


@router.post("/runs/{run_id}/plan/generate")
async def generate_plan(
    run_id: UUID,
    request: PlanGenerateRequest,
    background_tasks: BackgroundTasks,
    session: DbSession,
    current_user: CurrentUser,
):
    """
    Generate a Director JSON plan using the LLM.
    
    This starts a background job that will:
    1. Call the local LLM (Ollama)
    2. Validate the generated JSON
    3. Store the plan version
    4. Update the run status
    
    Returns immediately with job status.
    """
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    if run.plan_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot regenerate a locked plan"
        )
    
    # Update status to planning
    run.status = RunStatus.PLANNING
    run.progress = 0
    session.add(run)
    session.commit()
    
    # Enqueue the background job
    job_id = enqueue_director_job(
        run_id=run.id,
        project_id=project.id,
        user_id=current_user.id,
        request_data=request.model_dump(),
    )
    
    return {
        "status": "planning",
        "job_id": job_id,
        "message": "Plan generation started"
    }


@router.get("/runs/{run_id}/plan", response_model=DirectorPlanVersionRead)
async def get_current_plan(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get the current active plan for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    if not run.active_plan_version_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No plan generated yet"
        )
    
    version = session.get(DirectorPlanVersion, run.active_plan_version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan version not found"
        )
    
    return version


@router.patch("/runs/{run_id}/plan", response_model=DirectorPlanVersionRead)
async def update_plan(
    run_id: UUID,
    request: PlanUpdateRequest,
    session: DbSession,
    current_user: CurrentUser,
):
    """
    Update the current plan with changes.
    
    Creates a new version with the updates applied.
    """
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    if run.plan_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a locked plan"
        )
    
    try:
        updates = request.model_dump(exclude_unset=True)
        plan_version = director_service.update_plan(
            session=session,
            run=run,
            user_id=current_user.id,
            updates=updates,
            change_note=request.change_note,
        )
        return plan_version
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/runs/{run_id}/plan/approve")
async def approve_plan(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """
    Lock and approve the current plan.
    
    Once approved, the plan cannot be modified.
    The run status changes to APPROVED and is ready for generation.
    """
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    try:
        run = director_service.approve_plan(session, run)
        return {
            "status": "approved",
            "run_id": str(run.id),
            "plan_locked": run.plan_locked,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/runs/{run_id}/plan/versions", response_model=List[DirectorPlanVersionRead])
async def list_plan_versions(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all plan versions for a run."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    statement = select(DirectorPlanVersion).where(
        DirectorPlanVersion.run_id == run_id
    ).order_by(DirectorPlanVersion.version_number.desc())
    versions = session.exec(statement).all()
    
    return versions


@router.post("/runs/{run_id}/plan/versions/{version_id}/restore", response_model=DirectorPlanVersionRead)
async def restore_plan_version(
    run_id: UUID,
    version_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Restore a previous plan version."""
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    project = session.get(Project, run.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    try:
        plan_version = director_service.restore_plan_version(
            session=session,
            run=run,
            version_id=version_id,
            user_id=current_user.id,
        )
        return plan_version
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
