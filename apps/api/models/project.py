from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class AspectRatio(str, Enum):
    """Supported aspect ratios."""
    PORTRAIT = "9:16"
    SQUARE = "1:1"
    LANDSCAPE = "16:9"
    CUSTOM = "custom"


class Project(SQLModel, table=True):
    """Project model for organizing video reels."""
    
    __tablename__ = "projects"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(min_length=1, max_length=255)
    aspect_ratio: AspectRatio = Field(default=AspectRatio.PORTRAIT)
    duration_sec: int = Field(default=40, ge=5, le=180)
    storage_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProjectCreate(SQLModel):
    """Schema for creating a project."""
    name: str
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT
    duration_sec: int = 40


class ProjectUpdate(SQLModel):
    """Schema for updating a project."""
    name: Optional[str] = None
    aspect_ratio: Optional[AspectRatio] = None
    duration_sec: Optional[int] = None


class ProjectRead(SQLModel):
    """Schema for reading project data."""
    id: UUID
    user_id: UUID
    name: str
    aspect_ratio: AspectRatio
    duration_sec: int
    storage_path: Optional[str]
    created_at: datetime
    updated_at: datetime
