from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column, JSON


class RunStatus(str, Enum):
    """Run execution status."""
    DRAFT = "draft"
    PLANNING = "planning"      # LLM generating plan
    PLANNED = "planned"        # Plan generated, ready for review
    APPROVED = "approved"      # Plan locked, ready for generation
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class QualityProfile(str, Enum):
    """Quality profile for generation."""
    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"


class ReferenceStrategy(str, Enum):
    """Reference strategy for consistency."""
    HERO_ONLY = "hero_only"
    HERO_PLUS_PREV = "hero_plus_prev"
    CHARACTER_SHEET = "character_sheet"


class TransitionType(str, Enum):
    """Video transition type."""
    HARD_CUT = "hard_cut"
    FADE = "fade"
    DIP_TO_BLACK = "dip_to_black"


class Run(SQLModel, table=True):
    """A render attempt for a project."""
    
    __tablename__ = "runs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True)
    status: RunStatus = Field(default=RunStatus.DRAFT)
    progress: int = Field(default=0, ge=0, le=100)
    director_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    settings_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Phase 2: Plan management
    active_plan_version_id: Optional[UUID] = Field(default=None, foreign_key="director_plan_versions.id")
    plan_locked: bool = Field(default=False)
    
    # Phase 5: Quality settings
    quality_profile: QualityProfile = Field(default=QualityProfile.STANDARD)
    default_reference_strategy: ReferenceStrategy = Field(default=ReferenceStrategy.HERO_PLUS_PREV)
    default_variant_count: int = Field(default=3, ge=1, le=5)
    
    # Phase 5: Transition settings
    transition_type: TransitionType = Field(default=TransitionType.HARD_CUT)
    transition_frames: int = Field(default=0, ge=0, le=30)
    
    # Phase 5: Resumable pipeline
    node_status_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Phase 5: QC toggles
    qc_blur_check: bool = Field(default=True)
    qc_face_required: bool = Field(default=False)
    qc_no_text_warning: bool = Field(default=False)


class RunCreate(SQLModel):
    """Schema for creating a run."""
    settings_json: Optional[dict] = None


class RunUpdate(SQLModel):
    """Schema for updating a run."""
    quality_profile: Optional[QualityProfile] = None
    default_reference_strategy: Optional[ReferenceStrategy] = None
    default_variant_count: Optional[int] = None
    transition_type: Optional[TransitionType] = None
    transition_frames: Optional[int] = None
    qc_blur_check: Optional[bool] = None
    qc_face_required: Optional[bool] = None
    qc_no_text_warning: Optional[bool] = None


class RunRead(SQLModel):
    """Schema for reading run data."""
    id: UUID
    project_id: UUID
    status: RunStatus
    progress: int
    director_json: Optional[dict]
    settings_json: Optional[dict]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    active_plan_version_id: Optional[UUID]
    plan_locked: bool
    quality_profile: QualityProfile
    default_reference_strategy: ReferenceStrategy
    default_variant_count: int
    transition_type: TransitionType
    transition_frames: int
