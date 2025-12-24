"""
Image Generation Job Model

Tracks ComfyUI image generation jobs for hero frames and keyframes.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column, JSON


class ImageJobType(str, Enum):
    """Type of image generation job."""
    HERO_STYLE = "hero_style"
    HERO_CHARACTER = "hero_character"
    KEYFRAME = "keyframe"


class ImageJobStatus(str, Enum):
    """Image generation job status."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CACHED = "cached"


class ImageGenerationJob(SQLModel, table=True):
    """Tracks a single image generation job."""
    
    __tablename__ = "image_generation_jobs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    shot_id: Optional[UUID] = Field(default=None, foreign_key="shots.id", index=True)
    
    job_type: ImageJobType
    status: ImageJobStatus = Field(default=ImageJobStatus.QUEUED)
    
    # Caching / Idempotency
    idempotency_key: str = Field(index=True)
    input_hash: str
    
    # ComfyUI tracking
    comfy_prompt_id: Optional[str] = None
    
    # Results
    output_asset_id: Optional[UUID] = Field(default=None, foreign_key="assets.id")
    error_message: Optional[str] = None
    
    # Generation parameters (for reference)
    params_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ImageJobCreate(SQLModel):
    """Schema for creating an image job."""
    run_id: UUID
    shot_id: Optional[UUID] = None
    job_type: ImageJobType
    idempotency_key: str
    input_hash: str
    params_json: Optional[dict] = None


class ImageJobRead(SQLModel):
    """Schema for reading image job data."""
    id: UUID
    run_id: UUID
    shot_id: Optional[UUID]
    job_type: ImageJobType
    status: ImageJobStatus
    idempotency_key: str
    output_asset_id: Optional[UUID]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
