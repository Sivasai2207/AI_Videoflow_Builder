"""
System Models

Database models for system configuration, models registry, and performance profiles.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, Column, JSON


# ============================================================================
# Enums
# ============================================================================

class ModelType(str, Enum):
    """Type of AI model."""
    CHECKPOINT = "checkpoint"
    VAE = "vae"
    IPADAPTER = "ipadapter"
    CLIP_VISION = "clip_vision"
    VIDEO = "video"
    LLM = "llm"
    LORA = "lora"


class ModelStatus(str, Enum):
    """Model installation status."""
    NOT_INSTALLED = "not_installed"
    DOWNLOADING = "downloading"
    INSTALLED = "installed"
    INVALID = "invalid"


class RendererTarget(str, Enum):
    """Renderer execution target."""
    LOCAL_COMFYUI = "local_comfyui"
    REMOTE_GPU_WORKER = "remote_gpu_worker"


class CleanupPolicy(str, Enum):
    """Storage cleanup policy."""
    KEEP_ALL = "keep_all"
    KEEP_LAST_N = "keep_last_n"
    MAX_DISK_GB = "max_disk_gb"
    OLDER_THAN_DAYS = "older_than_days"


# ============================================================================
# Model Registry
# ============================================================================

class Model(SQLModel, table=True):
    """AI model registry entry."""
    __tablename__ = "models"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    type: ModelType
    version: str = Field(default="1.0")
    
    # Source
    source_url: Optional[str] = None
    huggingface_repo: Optional[str] = None
    
    # Local
    local_path: Optional[str] = None
    filename: Optional[str] = None
    
    # Verification
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    
    # Status
    status: ModelStatus = Field(default=ModelStatus.NOT_INSTALLED)
    last_verified_at: Optional[datetime] = None
    
    # Metadata
    required_for: Optional[str] = None  # "image", "video", "both"
    notes: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# System Settings (singleton-like, one row)
# ============================================================================

class SystemSettings(SQLModel, table=True):
    """Global system configuration."""
    __tablename__ = "system_settings"
    
    id: int = Field(default=1, primary_key=True)
    
    # Paths
    storage_root_path: str = Field(default="./data")
    comfyui_models_path: Optional[str] = None
    
    # Service URLs
    comfyui_url: str = Field(default="http://127.0.0.1:8188")
    redis_url: str = Field(default="redis://localhost:6379")
    ollama_url: str = Field(default="http://localhost:11434")
    
    # Renderer
    renderer_target_default: RendererTarget = Field(default=RendererTarget.LOCAL_COMFYUI)
    remote_worker_url: Optional[str] = None
    
    # Cleanup
    cleanup_policy: CleanupPolicy = Field(default=CleanupPolicy.KEEP_ALL)
    cleanup_keep_last_n: int = Field(default=10)
    cleanup_max_disk_gb: int = Field(default=50)
    cleanup_older_than_days: int = Field(default=30)
    
    # Performance
    active_performance_profile_id: Optional[UUID] = None
    
    # Security
    bind_host: str = Field(default="127.0.0.1")
    lan_mode_enabled: bool = Field(default=False)
    
    # Setup
    setup_completed: bool = Field(default=False)
    setup_completed_at: Optional[datetime] = None
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Performance Profile
# ============================================================================

class PerformanceProfile(SQLModel, table=True):
    """Performance benchmark results and safe defaults."""
    __tablename__ = "performance_profiles"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Machine info
    machine_name: str = Field(default="unknown")
    machine_chip: Optional[str] = None  # e.g., "Apple M1"
    machine_ram_gb: Optional[int] = None
    machine_gpu: Optional[str] = None
    
    # Benchmark results
    tested_at: datetime = Field(default_factory=datetime.utcnow)
    image_test_seconds: Optional[float] = None
    preview_video_test_seconds: Optional[float] = None
    final_video_test_seconds: Optional[float] = None
    
    # Safe defaults (stored as JSON)
    safe_defaults_json: dict = Field(default={}, sa_column=Column(JSON))
    
    # Example safe_defaults_json:
    # {
    #     "keyframe_width": 768,
    #     "keyframe_height": 1344,
    #     "keyframe_steps": 6,
    #     "keyframe_cfg": 4.0,
    #     "max_parallel_jobs": 1,
    #     "preview_duration_sec": 2,
    #     "final_clip_duration_sec": 4,
    # }
    
    is_active: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Default Models (seed data)
# ============================================================================

DEFAULT_REQUIRED_MODELS = [
    {
        "name": "SDXL Base",
        "type": ModelType.CHECKPOINT,
        "required_for": "image",
        "huggingface_repo": "stabilityai/stable-diffusion-xl-base-1.0",
        "filename": "sd_xl_base_1.0.safetensors",
        "notes": "Base SDXL checkpoint for image generation",
    },
    {
        "name": "SDXL VAE",
        "type": ModelType.VAE,
        "required_for": "image",
        "huggingface_repo": "stabilityai/sdxl-vae",
        "filename": "sdxl_vae.safetensors",
        "notes": "SDXL VAE for better color accuracy",
    },
    {
        "name": "IP-Adapter SDXL",
        "type": ModelType.IPADAPTER,
        "required_for": "image",
        "huggingface_repo": "h94/IP-Adapter",
        "filename": "ip-adapter_sdxl.safetensors",
        "notes": "IP-Adapter for character consistency",
    },
    {
        "name": "CLIP Vision",
        "type": ModelType.CLIP_VISION,
        "required_for": "image",
        "huggingface_repo": "openai/clip-vit-large-patch14",
        "filename": "clip_vision_g.safetensors",
        "notes": "CLIP vision encoder for IP-Adapter",
    },
    {
        "name": "Llama 3.2",
        "type": ModelType.LLM,
        "required_for": "both",
        "notes": "Local LLM for Director planning (via Ollama)",
    },
]
