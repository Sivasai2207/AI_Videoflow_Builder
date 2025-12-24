from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    """User account model."""
    
    __tablename__ = "users"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)


class UserCreate(SQLModel):
    """Schema for creating a user."""
    email: str
    password: str


class UserRead(SQLModel):
    """Schema for reading user data."""
    id: UUID
    email: str
    created_at: datetime
    is_active: bool


class Token(SQLModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(SQLModel):
    """Token payload data."""
    user_id: Optional[UUID] = None
