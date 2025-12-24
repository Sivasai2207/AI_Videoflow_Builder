from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class AssetType(str, Enum):
    """Asset file type."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    JSON = "json"


class AssetRole(str, Enum):
    """Asset role in the pipeline."""
    # Hero frames (Phase 3)
    HERO_FRAME_STYLE = "hero_frame_style"
    HERO_FRAME_CHARACTER = "hero_frame_character"
    # Keyframes (Phase 3)
    KEYFRAME = "keyframe"
    # Phase 5: Keyframe variants
    KEYFRAME_VARIANT = "keyframe_variant"
    # Video clips (Phase 4)
    PREVIEW_CLIP = "preview_clip"
    FINAL_CLIP = "final_clip"
    FINAL_VIDEO = "final_video"
    # References
    CHARACTER_SHEET = "character_sheet"
    STYLE_REFERENCE = "style_reference"
    # Legacy
    HERO_FRAME = "hero_frame"


class Asset(SQLModel, table=True):
    """Generated asset (image, video, etc.)."""
    
    __tablename__ = "assets"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    shot_id: Optional[UUID] = Field(default=None, foreign_key="shots.id")
    type: AssetType
    role: AssetRole
    file_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Phase 3: Generation metadata
    seed: Optional[int] = None
    model_id: Optional[str] = None
    version: int = Field(default=1)
    
    # Phase 5: Variant metadata
    variant_index: Optional[int] = None
    variant_group_id: Optional[UUID] = None


class AssetCreate(SQLModel):
    """Schema for creating an asset."""
    project_id: UUID
    run_id: UUID
    shot_id: Optional[UUID] = None
    type: AssetType
    role: AssetRole
    file_path: str
    seed: Optional[int] = None
    model_id: Optional[str] = None
    variant_index: Optional[int] = None
    variant_group_id: Optional[UUID] = None


class AssetRead(SQLModel):
    """Schema for reading asset data."""
    id: UUID
    project_id: UUID
    run_id: UUID
    shot_id: Optional[UUID]
    type: AssetType
    role: AssetRole
    file_path: str
    created_at: datetime
    seed: Optional[int]
    version: int
    variant_index: Optional[int]
