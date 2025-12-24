from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models.project import Project, ProjectCreate, ProjectUpdate, ProjectRead
from services.storage import get_project_path

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[ProjectRead])
async def list_projects(session: DbSession, current_user: CurrentUser):
    """List all projects for the current user."""
    statement = select(Project).where(Project.user_id == current_user.id).order_by(Project.created_at.desc())
    projects = session.exec(statement).all()
    return projects


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    session: DbSession,
    current_user: CurrentUser,
):
    """Create a new project."""
    project = Project(
        user_id=current_user.id,
        name=project_data.name,
        aspect_ratio=project_data.aspect_ratio,
        duration_sec=project_data.duration_sec,
    )
    
    session.add(project)
    session.commit()
    session.refresh(project)
    
    # Create storage directory and update path
    storage_path = get_project_path(project.id)
    project.storage_path = str(storage_path)
    session.add(project)
    session.commit()
    session.refresh(project)
    
    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Get a project by ID."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this project"
        )
    
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    session: DbSession,
    current_user: CurrentUser,
):
    """Update a project."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this project"
        )
    
    update_data = project_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    
    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)
    
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Delete a project."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this project"
        )
    
    session.delete(project)
    session.commit()
