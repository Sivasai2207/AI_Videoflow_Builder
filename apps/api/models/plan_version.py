from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column, JSON


class PlanStatus(str, Enum):
    """Plan version status."""
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class DirectorPlanVersion(SQLModel, table=True):
    """A versioned snapshot of a Director JSON plan."""
    
    __tablename__ = "director_plan_versions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    version_number: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: UUID = Field(foreign_key="users.id")
    director_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    change_note: Optional[str] = None
    status: PlanStatus = Field(default=PlanStatus.DRAFT)


class DirectorPlanVersionCreate(SQLModel):
    """Schema for creating a plan version."""
    director_json: dict
    change_note: Optional[str] = None


class DirectorPlanVersionRead(SQLModel):
    """Schema for reading plan version data."""
    id: UUID
    run_id: UUID
    version_number: int
    created_at: datetime
    created_by: UUID
    director_json: dict
    change_note: Optional[str]
    status: PlanStatus
