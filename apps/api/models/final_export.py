"""
Final Export Model

Tracks export jobs for different platforms.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class ExportPreset(str, Enum):
    """Export platform preset."""
    INSTAGRAM_REELS = "instagram_reels"
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    CUSTOM = "custom"


class ExportStatus(str, Enum):
    """Export job status."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FinalExport(SQLModel, table=True):
    """A final export job."""
    
    __tablename__ = "final_exports"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    preset: ExportPreset
    status: ExportStatus = Field(default=ExportStatus.QUEUED)
    
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    
    # Export settings
    width: int = Field(default=1080)
    height: int = Field(default=1920)
    fps: int = Field(default=30)
    bitrate_kbps: int = Field(default=8000)
    codec: str = Field(default="h264")
    
    # Audio settings
    include_voiceover: bool = Field(default=True)
    include_music: bool = Field(default=True)
    voiceover_volume: float = Field(default=1.0)
    music_volume: float = Field(default=0.3)
    
    error_message: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None


class FinalExportRead(SQLModel):
    """Schema for reading export data."""
    id: UUID
    run_id: UUID
    preset: ExportPreset
    status: ExportStatus
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    created_at: datetime
    finished_at: Optional[datetime]
