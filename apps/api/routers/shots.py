from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models.project import Project
from models.run import Run
from models.shot import Shot, ShotCreate, ShotUpdate, ShotRead

router = APIRouter(tags=["shots"])


@router.get("/runs/{run_id}/shots", response_model=List[ShotRead])
async def list_shots(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all shots in a run."""
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
    
    statement = select(Shot).where(Shot.run_id == run_id).order_by(Shot.order_index)
    shots = session.exec(statement).all()
    return shots


@router.post("/runs/{run_id}/shots", response_model=List[ShotRead], status_code=status.HTTP_201_CREATED)
async def create_shots(
    run_id: UUID,
    shots_data: List[ShotCreate],
    session: DbSession,
    current_user: CurrentUser,
):
    """Create placeholder shots for a run."""
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
    
    shots = []
    for i, shot_data in enumerate(shots_data):
        shot = Shot(
            project_id=run.project_id,
            run_id=run_id,
            order_index=shot_data.order_index if shot_data.order_index else i,
            duration_sec=shot_data.duration_sec,
        )
        session.add(shot)
        shots.append(shot)
    
    session.commit()
    for shot in shots:
        session.refresh(shot)
    
    return shots


@router.patch("/shots/{shot_id}", response_model=ShotRead)
async def update_shot(
    shot_id: UUID,
    shot_data: ShotUpdate,
    session: DbSession,
    current_user: CurrentUser,
):
    """Update a shot."""
    shot = session.get(Shot, shot_id)
    if not shot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shot not found"
        )
    
    project = session.get(Project, shot.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    update_data = shot_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(shot, key, value)
    
    session.add(shot)
    session.commit()
    session.refresh(shot)
    
    return shot
