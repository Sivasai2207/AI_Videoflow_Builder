"""
Audio Track Model

Tracks audio tracks (voiceover, music, mixed).
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class TrackType(str, Enum):
    """Type of audio track."""
    VOICEOVER = "voiceover"
    MUSIC = "music"
    MIXED = "mixed"


class AudioTrack(SQLModel, table=True):
    """An audio track for a run."""
    
    __tablename__ = "audio_tracks"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    track_type: TrackType
    file_path: str
    duration_sec: float = Field(default=0.0)
    
    # Voiceover-specific
    script_text: Optional[str] = None
    voice_id: Optional[str] = None
    
    # Music-specific
    music_name: Optional[str] = None
    volume_level: float = Field(default=1.0)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AudioTrackRead(SQLModel):
    """Schema for reading audio track data."""
    id: UUID
    run_id: UUID
    track_type: TrackType
    file_path: str
    duration_sec: float
    script_text: Optional[str]
    music_name: Optional[str]
    created_at: datetime
