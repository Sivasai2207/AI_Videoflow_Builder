from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlmodel import select

from dependencies import DbSession, CurrentUser
from models.project import Project
from models.run import Run
from models.asset import Asset, AssetRead

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}")
async def get_asset(
    asset_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """Download or stream an asset."""
    asset = session.get(Asset, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )
    
    project = session.get(Project, asset.project_id)
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    file_path = Path(asset.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset file not found"
        )
    
    return FileResponse(file_path)


@router.get("/runs/{run_id}/assets", response_model=List[AssetRead])
async def list_run_assets(
    run_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """List all assets for a run."""
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
    
    statement = select(Asset).where(Asset.run_id == run_id).order_by(Asset.created_at)
    assets = session.exec(statement).all()
    return assets
