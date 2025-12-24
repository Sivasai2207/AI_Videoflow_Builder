"""
Director JSON Schema

This module defines the complete Pydantic schema for the Director JSON,
which is the single source of truth for video generation.
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


# ============================================================================
# Enums
# ============================================================================

class Platform(str, Enum):
    INSTAGRAM_REELS = "instagram_reels"
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    CUSTOM = "custom"


class AspectRatioPreset(str, Enum):
    PORTRAIT = "9:16"
    SQUARE = "1:1"
    LANDSCAPE = "16:9"
    CUSTOM = "custom"


class Pacing(str, Enum):
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"


class StylePack(str, Enum):
    CINEMATIC = "cinematic"
    ANIME = "anime"
    PHOTOREAL = "photoreal"
    MINIMAL = "minimal"
    PIXEL = "pixel"
    CUSTOM = "custom"


class CameraType(str, Enum):
    CLOSE_UP = "close-up"
    WIDE = "wide"
    MEDIUM = "medium"
    MACRO = "macro"
    EXTREME_CLOSE_UP = "extreme-close-up"
    FULL_SHOT = "full-shot"


class CameraMove(str, Enum):
    PUSH_IN = "push-in"
    PULL_OUT = "pull-out"
    PAN = "pan"
    TILT = "tilt"
    STATIC = "static"
    DOLLY = "dolly"
    ORBIT = "orbit"
    CRANE = "crane"


class MotionIntent(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConsistencyPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReferenceStrategy(str, Enum):
    HERO_ONLY = "hero_only"
    HERO_PLUS_PREV = "hero_plus_prev"
    CHARACTER_SHEET = "character_sheet"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


# ============================================================================
# Sub-models
# ============================================================================

class ProjectConfig(BaseModel):
    """Project configuration."""
    platform: Platform = Platform.INSTAGRAM_REELS
    aspect_ratio: AspectRatioPreset = AspectRatioPreset.PORTRAIT
    width: int = Field(default=1080, ge=480, le=4096)
    height: int = Field(default=1920, ge=480, le=4096)
    fps: int = Field(default=30, ge=24, le=60)
    target_duration_sec: int = Field(default=40, ge=5, le=180)
    shot_count: int = Field(default=10, ge=4, le=20)
    pacing: Pacing = Pacing.MEDIUM


class StyleBible(BaseModel):
    """Visual style guidelines."""
    visual_keywords: List[str] = Field(default_factory=list)
    lighting: str = ""
    color_palette: str = ""
    lens_and_camera: str = ""
    composition_rules: List[str] = Field(default_factory=list)
    do_not_do: List[str] = Field(default_factory=list)


class Character(BaseModel):
    """Character definition for consistency."""
    name: str
    identity_tags: List[str] = Field(default_factory=list)
    consistency_priority: ConsistencyPriority = ConsistencyPriority.MEDIUM


class CreativeConfig(BaseModel):
    """Creative direction configuration."""
    title: str = ""
    logline: str = ""
    genre: str = ""
    style_pack: StylePack = StylePack.CINEMATIC
    style_bible: StyleBible = Field(default_factory=StyleBible)
    characters: List[Character] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)


class SafetyConfig(BaseModel):
    """Content safety configuration."""
    platform_safe_mode: bool = True
    avoid: List[str] = Field(default_factory=lambda: ["nudity", "hate", "extreme_gore", "illegal"])
    notes: str = ""


class SeedPolicy(BaseModel):
    """Seed generation policy for reproducibility."""
    base_seed: int = Field(default=123456)
    per_shot_offset: int = Field(default=17)


class ConsistencyConfig(BaseModel):
    """Consistency strategy for image generation."""
    use_hero_frame: bool = True
    use_ip_adapter: bool = True
    reference_strategy: ReferenceStrategy = ReferenceStrategy.HERO_ONLY


class GenerationConfig(BaseModel):
    """Generation settings."""
    seed_policy: SeedPolicy = Field(default_factory=SeedPolicy)
    consistency: ConsistencyConfig = Field(default_factory=ConsistencyConfig)
    negative_prompt_global: str = "blurry, low quality, distorted, ugly, bad anatomy, watermark, text, logo"


class CameraConfig(BaseModel):
    """Camera configuration for a shot."""
    type: CameraType = CameraType.MEDIUM
    move: CameraMove = CameraMove.STATIC
    notes: str = ""


class ShotConfig(BaseModel):
    """Individual shot configuration."""
    shot_id: str
    duration_sec: int = Field(default=4, ge=1, le=30)
    timestamp_start_sec: float = 0
    timestamp_end_sec: float = 4
    camera: CameraConfig = Field(default_factory=CameraConfig)
    action_beats: List[str] = Field(default_factory=list)
    prompt: str
    negative_prompt: str = ""
    motion_intent: MotionIntent = MotionIntent.MEDIUM
    keyframe_notes: str = ""
    seed: int = 0
    
    # Lock flags for Phase 3
    lock_seed: bool = False
    lock_character_style: bool = False
    lock_prompt_structure: bool = False


# ============================================================================
# Main Director JSON Model
# ============================================================================

class DirectorJSON(BaseModel):
    """
    Complete Director JSON schema.
    
    This is the single source of truth for video generation.
    Everything needed to reproduce a render is stored here.
    """
    schema_version: str = "1.0"
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    creative: CreativeConfig = Field(default_factory=CreativeConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    shots: List[ShotConfig] = Field(default_factory=list)
    
    @model_validator(mode='after')
    def validate_shots(self) -> 'DirectorJSON':
        """Validate shot configuration."""
        if not self.shots:
            return self
        
        # Check shot count
        if len(self.shots) != self.project.shot_count:
            # Auto-fix: update shot_count to match actual shots
            self.project.shot_count = len(self.shots)
        
        # Validate and fix timestamps
        current_time = 0.0
        for i, shot in enumerate(self.shots):
            shot.shot_id = f"S{i+1:02d}"
            shot.timestamp_start_sec = current_time
            shot.timestamp_end_sec = current_time + shot.duration_sec
            current_time = shot.timestamp_end_sec
            
            # Compute seed from policy if not set or zero
            if shot.seed == 0:
                shot.seed = self.generation.seed_policy.base_seed + (i * self.generation.seed_policy.per_shot_offset)
        
        return self


# ============================================================================
# Validation Functions
# ============================================================================

def validate_director_json(data: dict) -> tuple[DirectorJSON, List[str]]:
    """
    Validate a Director JSON dictionary.
    
    Returns:
        Tuple of (parsed DirectorJSON, list of validation errors)
    """
    errors = []
    
    try:
        director = DirectorJSON.model_validate(data)
    except Exception as e:
        return None, [str(e)]
    
    # Check duration sum
    total_duration = sum(shot.duration_sec for shot in director.shots)
    target = director.project.target_duration_sec
    if abs(total_duration - target) > 1:
        errors.append(f"Total shot duration ({total_duration}s) differs from target ({target}s) by more than 1s")
    
    # Check all shots have prompts
    for i, shot in enumerate(director.shots):
        if not shot.prompt or not shot.prompt.strip():
            errors.append(f"Shot {i+1} is missing a prompt")
    
    # Check platform safety
    if director.safety.platform_safe_mode:
        avoid_terms = director.safety.avoid
        for i, shot in enumerate(director.shots):
            prompt_lower = shot.prompt.lower()
            for term in avoid_terms:
                if term.lower() in prompt_lower:
                    errors.append(f"Shot {i+1} prompt contains avoided term: '{term}'")
    
    return director, errors


# ============================================================================
# API Request/Response Models
# ============================================================================

class PlanGenerateRequest(BaseModel):
    """Request body for generating a plan."""
    concept: str = Field(..., min_length=10, max_length=2000)
    style_pack: StylePack = StylePack.CINEMATIC
    pacing: Pacing = Pacing.MEDIUM
    platform: Platform = Platform.INSTAGRAM_REELS
    aspect_ratio: AspectRatioPreset = AspectRatioPreset.PORTRAIT
    target_duration_sec: int = Field(default=40, ge=15, le=120)
    constraints: List[str] = Field(default_factory=list)
    
    # Optional overrides
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None
    fps: int = 30


class PlanUpdateRequest(BaseModel):
    """Request body for updating a plan."""
    # Shot updates (partial)
    shots: Optional[List[dict]] = None  # List of partial shot updates
    
    # Global updates
    creative: Optional[dict] = None
    safety: Optional[dict] = None
    generation: Optional[dict] = None
    
    # Change tracking
    change_note: Optional[str] = None
