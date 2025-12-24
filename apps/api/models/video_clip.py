"""
Video Clip Model

Tracks generated video clips (preview, final, stitched).
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class ClipType(str, Enum):
    """Type of video clip."""
    PREVIEW = "preview"
    FINAL = "final"
    STITCHED = "stitched"


class VideoClipStatus(str, Enum):
    """Video clip generation status."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VideoClip(SQLModel, table=True):
    """A generated video clip."""
    
    __tablename__ = "video_clips"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    shot_id: Optional[UUID] = Field(default=None, foreign_key="shots.id", index=True)
    
    clip_type: ClipType
    status: VideoClipStatus = Field(default=VideoClipStatus.QUEUED)
    
    file_path: Optional[str] = None
    duration_sec: float = Field(default=0.0)
    
    # Generation metadata
    keyframe_asset_id: Optional[UUID] = Field(default=None, foreign_key="assets.id")
    fps: int = Field(default=30)
    width: int = Field(default=768)
    height: int = Field(default=1344)
    
    error_message: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None


class VideoClipRead(SQLModel):
    """Schema for reading video clip data."""
    id: UUID
    run_id: UUID
    shot_id: Optional[UUID]
    clip_type: ClipType
    status: VideoClipStatus
    file_path: Optional[str]
    duration_sec: float
    created_at: datetime
