import asyncio
import json
from datetime import datetime
from typing import List, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models.project import Project
from models.run import Run, RunCreate, RunRead, RunStatus
from models.render_job import RenderJob, JobStatus
from services.queue import enqueue_pipeline_job
from services.storage import get_run_path

router = APIRouter(tags=["runs"])


@router.post("/projects/{project_id}/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(
    project_id: UUID,
    run_data: RunCreate,
    session: DbSession,
    current_user: CurrentUser,
):
    """Create a new run for a project."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    run = Run(
        project_id=project_id,
        settings_json=run_data.settings_json,
    )
    
    session.add(run)
    session.commit()
    session.refresh(run)
    
    # Create storage directory
    get_run_path(project_id, run.id)
    
    return run


@router.get("/projects/{project_id}/runs", response_model=List[RunRead])
async def list_runs(
    project_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all runs for a project."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    statement = select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc())
    runs = session.exec(statement).all()
    return runs


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get a run by ID."""
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
    
    return run


@router.post("/runs/{run_id}/start", response_model=RunRead)
async def start_run(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Start a run's execution."""
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
    
    if run.status not in [RunStatus.DRAFT, RunStatus.FAILED, RunStatus.CANCELED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start run with status: {run.status}"
        )
    
    # Update run status
    run.status = RunStatus.QUEUED
    run.progress = 0
    run.started_at = datetime.utcnow()
    session.add(run)
    
    # Create render job
    job = RenderJob(
        run_id=run.id,
        node_name="simulate_pipeline",
        status=JobStatus.QUEUED,
    )
    
    # Enqueue the background job
    rq_job_id = enqueue_pipeline_job(run.id, project.id)
    job.rq_job_id = rq_job_id
    
    session.add(job)
    session.commit()
    session.refresh(run)
    
    return run


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Cancel a running job."""
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
    
    if run.status not in [RunStatus.QUEUED, RunStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel run with status: {run.status}"
        )
    
    run.status = RunStatus.CANCELED
    run.finished_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    
    return run


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Stream run progress events via SSE."""
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
    
    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for run progress."""
        last_progress = -1
        last_status = None
        
        while True:
            # Refresh run data
            session.refresh(run)
            
            # Send update if changed
            if run.progress != last_progress or run.status != last_status:
                last_progress = run.progress
                last_status = run.status
                
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "run_id": str(run.id),
                        "status": run.status.value,
                        "progress": run.progress,
                    })
                }
            
            # Stop if run is complete
            if run.status in [RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELED]:
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "run_id": str(run.id),
                        "status": run.status.value,
                        "progress": run.progress,
                    })
                }
                break
            
            await asyncio.sleep(0.5)
    
    return EventSourceResponse(event_generator())
