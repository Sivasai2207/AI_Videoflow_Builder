from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class JobStatus(str, Enum):
    """Job execution status."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RenderJob(SQLModel, table=True):
    """Background job for rendering."""
    
    __tablename__ = "render_jobs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    node_name: str = Field(default="simulate_pipeline")
    status: JobStatus = Field(default=JobStatus.QUEUED)
    progress: int = Field(default=0, ge=0, le=100)
    logs_path: Optional[str] = None
    rq_job_id: Optional[str] = None


class RenderJobRead(SQLModel):
    """Schema for reading job data."""
    id: UUID
    run_id: UUID
    node_name: str
    status: JobStatus
    progress: int
    logs_path: Optional[str]
