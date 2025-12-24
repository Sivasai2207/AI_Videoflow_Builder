"""
Director Service

Handles Director JSON generation, validation, and plan versioning.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List
from uuid import UUID

from sqlmodel import Session, select

from config import PROJECTS_DIR
from models import Run, RunStatus, DirectorPlanVersion, PlanStatus
from schemas.director import (
    DirectorJSON,
    PlanGenerateRequest,
    validate_director_json,
    StylePack,
    Pacing,
    Platform,
    AspectRatioPreset,
)
from services import ollama


# ============================================================================
# Prompt Templates
# ============================================================================

SYSTEM_PROMPT = """You are a film director and storyboard generator for short-form video content.

CRITICAL RULES:
1. Return ONLY valid JSON matching the schema - no markdown, no commentary, no explanations
2. Shots MUST sum to exactly target_duration_sec (±1 second allowed)
3. Every shot MUST have a detailed prompt and negative_prompt
4. When platform_safe_mode is true, prompts MUST be family-friendly
5. Generate exactly shot_count number of shots
6. Timestamps must be sequential (each shot starts where previous ends)

You will receive a concept and requirements. Generate a complete Director JSON following the schema exactly."""


def build_user_prompt(request: PlanGenerateRequest) -> str:
    """Build the user prompt for plan generation."""
    
    # Calculate shot distribution based on pacing
    if request.pacing == Pacing.FAST:
        shot_count = 12
        avg_duration = request.target_duration_sec / 12
    elif request.pacing == Pacing.SLOW:
        shot_count = 8
        avg_duration = request.target_duration_sec / 8
    else:  # MEDIUM
        shot_count = 10
        avg_duration = request.target_duration_sec / 10
    
    # Map aspect ratio to dimensions
    dimensions = {
        AspectRatioPreset.PORTRAIT: (1080, 1920),
        AspectRatioPreset.SQUARE: (1080, 1080),
        AspectRatioPreset.LANDSCAPE: (1920, 1080),
    }
    width, height = dimensions.get(request.aspect_ratio, (1080, 1920))
    if request.custom_width and request.custom_height:
        width, height = request.custom_width, request.custom_height
    
    # Style pack descriptions
    style_descriptions = {
        StylePack.CINEMATIC: "cinematic film look, dramatic lighting, shallow depth of field, movie-like composition",
        StylePack.ANIME: "anime art style, vibrant colors, dynamic poses, expressive characters, cel-shaded look",
        StylePack.PHOTOREAL: "photorealistic, highly detailed, natural lighting, lifelike textures, DSLR quality",
        StylePack.MINIMAL: "minimalist aesthetic, clean lines, simple compositions, muted colors, elegant simplicity",
        StylePack.PIXEL: "pixel art style, retro gaming aesthetic, 8-bit/16-bit look, nostalgic",
        StylePack.CUSTOM: "custom style as specified in concept",
    }
    
    constraints_text = ""
    if request.constraints:
        constraints_text = f"\nConstraints to follow:\n" + "\n".join(f"- {c}" for c in request.constraints)
    
    return f"""Generate a Director JSON for this video concept:

CONCEPT: {request.concept}

REQUIREMENTS:
- Platform: {request.platform.value}
- Aspect Ratio: {request.aspect_ratio.value} ({width}x{height})
- Target Duration: {request.target_duration_sec} seconds
- Shot Count: {shot_count} shots
- Average Shot Duration: {avg_duration:.1f} seconds (can vary per shot)
- Pacing: {request.pacing.value}
- Style: {style_descriptions.get(request.style_pack, "cinematic")}
- FPS: {request.fps}
{constraints_text}

SCHEMA (follow exactly):
{{
  "schema_version": "1.0",
  "project": {{
    "platform": "{request.platform.value}",
    "aspect_ratio": "{request.aspect_ratio.value}",
    "width": {width},
    "height": {height},
    "fps": {request.fps},
    "target_duration_sec": {request.target_duration_sec},
    "shot_count": {shot_count},
    "pacing": "{request.pacing.value}"
  }},
  "creative": {{
    "title": "string",
    "logline": "one-line summary",
    "genre": "string",
    "style_pack": "{request.style_pack.value}",
    "style_bible": {{
      "visual_keywords": ["keyword1", "keyword2", ...],
      "lighting": "describe lighting style",
      "color_palette": "describe color scheme",
      "lens_and_camera": "describe camera/lens style",
      "composition_rules": ["rule1", "rule2"],
      "do_not_do": ["avoid this", "avoid that"]
    }},
    "characters": [
      {{
        "name": "character name",
        "identity_tags": ["hair:description", "outfit:description", "age:range"],
        "consistency_priority": "high"
      }}
    ],
    "locations": ["location1", "location2"]
  }},
  "safety": {{
    "platform_safe_mode": true,
    "avoid": ["nudity", "hate", "extreme_gore", "illegal"],
    "notes": ""
  }},
  "generation": {{
    "seed_policy": {{
      "base_seed": 123456,
      "per_shot_offset": 17
    }},
    "consistency": {{
      "use_hero_frame": true,
      "use_ip_adapter": true,
      "reference_strategy": "hero_only"
    }},
    "negative_prompt_global": "blurry, low quality, distorted, ugly, watermark, text"
  }},
  "shots": [
    {{
      "shot_id": "S01",
      "duration_sec": 4,
      "timestamp_start_sec": 0,
      "timestamp_end_sec": 4,
      "camera": {{
        "type": "medium|close-up|wide|macro",
        "move": "static|push-in|pan|tilt",
        "notes": ""
      }},
      "action_beats": ["what happens in this shot"],
      "prompt": "detailed image generation prompt for this shot",
      "negative_prompt": "what to avoid in this shot",
      "motion_intent": "low|medium|high",
      "keyframe_notes": "",
      "seed": 123456
    }}
  ]
}}

Generate {shot_count} shots that tell a complete visual story. Each shot prompt should be detailed enough for image generation (50-150 words).

Return ONLY the JSON, no other text."""


def build_repair_prompt(errors: List[str], original_json: dict) -> str:
    """Build a repair prompt for fixing validation errors."""
    return f"""The Director JSON you generated has validation errors:

ERRORS:
{chr(10).join(f"- {e}" for e in errors)}

ORIGINAL JSON:
{json.dumps(original_json, indent=2)}

Please fix these errors and return the corrected JSON. 
Remember: shots must sum to target_duration_sec, and every shot needs a prompt.
Return ONLY the corrected JSON, no other text."""


# ============================================================================
# Plan Generation
# ============================================================================

async def generate_plan(
    session: Session,
    run: Run,
    user_id: UUID,
    request: PlanGenerateRequest,
) -> Tuple[DirectorPlanVersion, List[str]]:
    """
    Generate a Director JSON plan using the LLM.
    
    Args:
        session: Database session
        run: The run to generate a plan for
        user_id: ID of the user generating the plan
        request: Plan generation request
        
    Returns:
        Tuple of (created plan version, any validation warnings)
    """
    warnings = []
    
    # Build prompts
    user_prompt = build_user_prompt(request)
    
    # Generate with LLM
    try:
        raw_json = await ollama.generate_json(user_prompt, SYSTEM_PROMPT)
    except ValueError as e:
        raise ValueError(f"LLM failed to generate valid JSON: {e}")
    
    # Validate
    director, errors = validate_director_json(raw_json)
    
    # If errors, try repair
    if errors and director is None:
        repair_prompt = build_repair_prompt(errors, raw_json)
        try:
            raw_json = await ollama.generate_json(repair_prompt, SYSTEM_PROMPT)
            director, errors = validate_director_json(raw_json)
        except ValueError:
            pass
    
    # If still no valid director, raise
    if director is None:
        raise ValueError(f"Failed to generate valid plan: {', '.join(errors)}")
    
    # Convert to dict for storage
    director_dict = director.model_dump()
    
    # Store warnings (non-fatal errors)
    if errors:
        warnings = errors
    
    # Get next version number
    statement = select(DirectorPlanVersion).where(
        DirectorPlanVersion.run_id == run.id
    ).order_by(DirectorPlanVersion.version_number.desc())
    existing = session.exec(statement).first()
    next_version = (existing.version_number + 1) if existing else 1
    
    # Create plan version
    plan_version = DirectorPlanVersion(
        run_id=run.id,
        version_number=next_version,
        created_by=user_id,
        director_json=director_dict,
        status=PlanStatus.DRAFT,
    )
    session.add(plan_version)
    
    # Update run
    run.director_json = director_dict
    run.active_plan_version_id = plan_version.id
    run.status = RunStatus.PLANNED
    session.add(run)
    
    session.commit()
    session.refresh(plan_version)
    
    # Save to disk
    save_plan_to_disk(run.project_id, run.id, plan_version)
    
    return plan_version, warnings


def save_plan_to_disk(project_id: UUID, run_id: UUID, plan_version: DirectorPlanVersion) -> Path:
    """Save a plan version to disk."""
    run_path = PROJECTS_DIR / str(project_id) / "runs" / str(run_id) / "plan"
    run_path.mkdir(parents=True, exist_ok=True)
    
    # Save current version
    current_path = run_path / f"director_v{plan_version.version_number}.json"
    with open(current_path, "w") as f:
        json.dump(plan_version.director_json, f, indent=2)
    
    # Also save as "current"
    latest_path = run_path / "director_current.json"
    with open(latest_path, "w") as f:
        json.dump(plan_version.director_json, f, indent=2)
    
    return current_path


def update_plan(
    session: Session,
    run: Run,
    user_id: UUID,
    updates: dict,
    change_note: Optional[str] = None,
) -> DirectorPlanVersion:
    """
    Update the current plan with changes.
    
    Creates a new version with the updates applied.
    """
    if run.plan_locked:
        raise ValueError("Cannot update a locked plan")
    
    if not run.director_json:
        raise ValueError("No plan to update")
    
    # Apply updates to current JSON
    current = run.director_json.copy()
    
    # Update shots if provided
    if "shots" in updates and updates["shots"]:
        for shot_update in updates["shots"]:
            shot_id = shot_update.get("shot_id")
            if shot_id:
                for i, shot in enumerate(current.get("shots", [])):
                    if shot.get("shot_id") == shot_id:
                        current["shots"][i].update(shot_update)
                        break
    
    # Update other sections
    for section in ["creative", "safety", "generation"]:
        if section in updates and updates[section]:
            if section in current:
                current[section].update(updates[section])
            else:
                current[section] = updates[section]
    
    # Validate updated JSON
    director, errors = validate_director_json(current)
    if director is None:
        raise ValueError(f"Invalid plan after update: {', '.join(errors)}")
    
    # Get next version number
    statement = select(DirectorPlanVersion).where(
        DirectorPlanVersion.run_id == run.id
    ).order_by(DirectorPlanVersion.version_number.desc())
    existing = session.exec(statement).first()
    next_version = (existing.version_number + 1) if existing else 1
    
    # Create new version
    plan_version = DirectorPlanVersion(
        run_id=run.id,
        version_number=next_version,
        created_by=user_id,
        director_json=director.model_dump(),
        change_note=change_note,
        status=PlanStatus.DRAFT,
    )
    session.add(plan_version)
    
    # Update run
    run.director_json = plan_version.director_json
    run.active_plan_version_id = plan_version.id
    session.add(run)
    
    session.commit()
    session.refresh(plan_version)
    
    # Save to disk
    save_plan_to_disk(run.project_id, run.id, plan_version)
    
    return plan_version


def approve_plan(session: Session, run: Run) -> Run:
    """Lock and approve the current plan."""
    if not run.director_json:
        raise ValueError("No plan to approve")
    
    if run.plan_locked:
        raise ValueError("Plan is already approved")
    
    # Update active version status
    if run.active_plan_version_id:
        version = session.get(DirectorPlanVersion, run.active_plan_version_id)
        if version:
            version.status = PlanStatus.APPROVED
            session.add(version)
    
    # Lock the plan
    run.plan_locked = True
    run.status = RunStatus.APPROVED
    session.add(run)
    
    session.commit()
    session.refresh(run)
    
    return run


def restore_plan_version(
    session: Session,
    run: Run,
    version_id: UUID,
    user_id: UUID,
) -> DirectorPlanVersion:
    """Restore a previous plan version."""
    if run.plan_locked:
        raise ValueError("Cannot restore to a locked plan")
    
    # Get the version to restore
    old_version = session.get(DirectorPlanVersion, version_id)
    if not old_version or old_version.run_id != run.id:
        raise ValueError("Version not found")
    
    # Create new version from old
    statement = select(DirectorPlanVersion).where(
        DirectorPlanVersion.run_id == run.id
    ).order_by(DirectorPlanVersion.version_number.desc())
    latest = session.exec(statement).first()
    next_version = (latest.version_number + 1) if latest else 1
    
    plan_version = DirectorPlanVersion(
        run_id=run.id,
        version_number=next_version,
        created_by=user_id,
        director_json=old_version.director_json,
        change_note=f"Restored from v{old_version.version_number}",
        status=PlanStatus.DRAFT,
    )
    session.add(plan_version)
    
    # Update run
    run.director_json = plan_version.director_json
    run.active_plan_version_id = plan_version.id
    session.add(run)
    
    session.commit()
    session.refresh(plan_version)
    
    # Save to disk
    save_plan_to_disk(run.project_id, run.id, plan_version)
    
    return plan_version
