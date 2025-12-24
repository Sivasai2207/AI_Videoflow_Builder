from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column, JSON


class ShotStatus(str, Enum):
    """Shot generation status."""
    DRAFT = "draft"
    GENERATED = "generated"
    APPROVED = "approved"


class KeyframeStatus(str, Enum):
    """Keyframe generation status."""
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    GENERATED = "generated"
    APPROVED = "approved"
    FAILED = "failed"


class QCStatus(str, Enum):
    """Quality control status."""
    NOT_RUN = "not_run"
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Shot(SQLModel, table=True):
    """A single shot within a run."""
    
    __tablename__ = "shots"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    order_index: int = Field(default=0)
    duration_sec: int = Field(default=4, ge=1, le=30)
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    status: ShotStatus = Field(default=ShotStatus.DRAFT)
    
    # Phase 3: Keyframe generation fields
    keyframe_asset_id: Optional[UUID] = Field(default=None, foreign_key="assets.id")
    keyframe_status: KeyframeStatus = Field(default=KeyframeStatus.NOT_STARTED)
    keyframe_seed: Optional[int] = None
    keyframe_model_id: Optional[str] = None
    keyframe_params_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Phase 5: Variants
    selected_variant_asset_id: Optional[UUID] = Field(default=None, foreign_key="assets.id")
    variant_group_id: Optional[UUID] = None
    variant_count: int = Field(default=1)
    
    # Phase 5: QC
    qc_status: QCStatus = Field(default=QCStatus.NOT_RUN)
    qc_warnings_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Phase 5: Per-shot override
    reference_strategy: Optional[str] = None


class ShotCreate(SQLModel):
    """Schema for creating shots."""
    order_index: int = 0
    duration_sec: int = 4


class ShotUpdate(SQLModel):
    """Schema for updating a shot."""
    order_index: Optional[int] = None
    duration_sec: Optional[int] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    status: Optional[ShotStatus] = None
    keyframe_status: Optional[KeyframeStatus] = None
    qc_status: Optional[QCStatus] = None
    reference_strategy: Optional[str] = None


class ShotRead(SQLModel):
    """Schema for reading shot data."""
    id: UUID
    project_id: UUID
    run_id: UUID
    order_index: int
    duration_sec: int
    prompt: Optional[str]
    negative_prompt: Optional[str]
    seed: Optional[int]
    status: ShotStatus
    keyframe_asset_id: Optional[UUID]
    keyframe_status: KeyframeStatus
    keyframe_seed: Optional[int]
    qc_status: QCStatus
    qc_warnings_json: Optional[dict]
    selected_variant_asset_id: Optional[UUID]
    variant_count: int
    reference_strategy: Optional[str]
