"""
Image Generation Service

Handles hero frame and keyframe generation with ComfyUI.
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from uuid import UUID

from sqlmodel import Session, select

from config import PROJECTS_DIR, BASE_DIR
from models import (
    Run, Shot, Asset, AssetType, AssetRole,
    ImageGenerationJob, ImageJobType, ImageJobStatus,
)
from models.shot import KeyframeStatus


# Default generation parameters
DEFAULT_PARAMS = {
    "width": 768,
    "height": 1344,
    "steps": 6,
    "cfg": 3.5,
    "checkpoint": "sd_xl_base_1.0.safetensors",
}

WORKFLOWS_DIR = BASE_DIR / "workflows" / "templates"


def compute_idempotency_key(
    run_id: str,
    shot_id: Optional[str],
    job_type: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    model_id: str,
    ref_asset_ids: List[str] = None,
) -> str:
    """Compute idempotency key for caching."""
    data = f"{run_id}:{shot_id}:{job_type}:{prompt}:{negative_prompt}:{seed}:{width}:{height}:{steps}:{cfg}:{model_id}"
    if ref_asset_ids:
        data += ":" + ":".join(sorted(ref_asset_ids))
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def compute_input_hash(params: dict) -> str:
    """Compute hash of input parameters."""
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:32]


def get_images_dir(project_id: UUID, run_id: UUID) -> Path:
    """Get images directory for a run."""
    path = PROJECTS_DIR / str(project_id) / "runs" / str(run_id) / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_hero_dir(project_id: UUID, run_id: UUID) -> Path:
    """Get hero frames directory."""
    path = get_images_dir(project_id, run_id) / "hero"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_shot_dir(project_id: UUID, run_id: UUID, shot_id: str) -> Path:
    """Get shot images directory."""
    path = get_images_dir(project_id, run_id) / "shots" / shot_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def check_cache(
    session: Session,
    idempotency_key: str,
) -> Optional[ImageGenerationJob]:
    """Check if a job with this idempotency key already exists and succeeded."""
    statement = select(ImageGenerationJob).where(
        ImageGenerationJob.idempotency_key == idempotency_key,
        ImageGenerationJob.status == ImageJobStatus.SUCCEEDED,
    )
    return session.exec(statement).first()


def create_image_job(
    session: Session,
    run_id: UUID,
    job_type: ImageJobType,
    idempotency_key: str,
    input_hash: str,
    shot_id: Optional[UUID] = None,
    params: Optional[dict] = None,
) -> ImageGenerationJob:
    """Create a new image generation job."""
    job = ImageGenerationJob(
        run_id=run_id,
        shot_id=shot_id,
        job_type=job_type,
        idempotency_key=idempotency_key,
        input_hash=input_hash,
        params_json=params,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def register_asset(
    session: Session,
    project_id: UUID,
    run_id: UUID,
    file_path: str,
    role: AssetRole,
    shot_id: Optional[UUID] = None,
    seed: Optional[int] = None,
    model_id: Optional[str] = None,
) -> Asset:
    """Register a generated asset in the database."""
    # Get next version for this shot/role
    if shot_id:
        statement = select(Asset).where(
            Asset.run_id == run_id,
            Asset.shot_id == shot_id,
            Asset.role == role,
        )
        existing = session.exec(statement).all()
        version = len(existing) + 1
    else:
        version = 1
    
    asset = Asset(
        project_id=project_id,
        run_id=run_id,
        shot_id=shot_id,
        type=AssetType.IMAGE,
        role=role,
        file_path=file_path,
        seed=seed,
        model_id=model_id,
        version=version,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def build_hero_prompt(director_json: dict) -> tuple[str, str]:
    """Build hero frame prompt from Director JSON."""
    creative = director_json.get("creative", {})
    style_bible = creative.get("style_bible", {})
    
    # Build style prompt
    keywords = style_bible.get("visual_keywords", [])
    lighting = style_bible.get("lighting", "")
    palette = style_bible.get("color_palette", "")
    lens = style_bible.get("lens_and_camera", "")
    
    prompt_parts = [
        creative.get("logline", ""),
        ", ".join(keywords),
        lighting,
        palette,
        lens,
        "masterpiece, best quality, highly detailed",
    ]
    prompt = ", ".join(filter(None, prompt_parts))
    
    # Build negative prompt
    do_not_do = style_bible.get("do_not_do", [])
    generation = director_json.get("generation", {})
    negative_global = generation.get("negative_prompt_global", "")
    
    negative_parts = do_not_do + [negative_global] if negative_global else do_not_do
    negative_prompt = ", ".join(filter(None, negative_parts))
    
    return prompt, negative_prompt


def build_character_prompt(director_json: dict) -> tuple[str, str]:
    """Build character anchor prompt from Director JSON."""
    creative = director_json.get("creative", {})
    style_bible = creative.get("style_bible", {})
    characters = creative.get("characters", [])
    
    # Use first character if available
    char_desc = ""
    if characters:
        char = characters[0]
        char_desc = f"{char.get('name', 'character')}, " + ", ".join(char.get("identity_tags", []))
    
    keywords = style_bible.get("visual_keywords", [])
    
    prompt_parts = [
        char_desc,
        ", ".join(keywords),
        "full body portrait, centered composition",
        "masterpiece, best quality, highly detailed",
    ]
    prompt = ", ".join(filter(None, prompt_parts))
    
    # Negative
    generation = director_json.get("generation", {})
    negative_prompt = generation.get("negative_prompt_global", "blurry, low quality, distorted")
    
    return prompt, negative_prompt


def build_keyframe_prompt(shot: dict, director_json: dict) -> tuple[str, str]:
    """Build keyframe prompt from shot and Director JSON."""
    # Shot-specific prompt
    shot_prompt = shot.get("prompt", "")
    shot_negative = shot.get("negative_prompt", "")
    
    # Add style keywords
    creative = director_json.get("creative", {})
    style_bible = creative.get("style_bible", {})
    keywords = style_bible.get("visual_keywords", [])
    
    prompt = shot_prompt
    if keywords:
        prompt += ", " + ", ".join(keywords)
    prompt += ", masterpiece, best quality"
    
    # Combine negative prompts
    generation = director_json.get("generation", {})
    global_negative = generation.get("negative_prompt_global", "")
    
    if shot_negative and global_negative:
        negative = f"{shot_negative}, {global_negative}"
    else:
        negative = shot_negative or global_negative
    
    return prompt, negative


def build_workflow(
    template_name: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    filename_prefix: str,
    width: int = DEFAULT_PARAMS["width"],
    height: int = DEFAULT_PARAMS["height"],
    steps: int = DEFAULT_PARAMS["steps"],
    cfg: float = DEFAULT_PARAMS["cfg"],
    checkpoint: str = DEFAULT_PARAMS["checkpoint"],
) -> dict:
    """Build a ComfyUI workflow from template."""
    template_path = WORKFLOWS_DIR / f"{template_name}.json"
    
    if not template_path.exists():
        # Return a mock workflow for testing
        return {
            "mock": True,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
        }
    
    with open(template_path) as f:
        workflow_str = f.read()
    
    # Replace placeholders
    replacements = {
        "CHECKPOINT_NAME": checkpoint,
        "PROMPT": prompt.replace('"', '\\"'),
        "NEGATIVE_PROMPT": negative_prompt.replace('"', '\\"'),
        "SEED": str(seed),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "STEPS": str(steps),
        "CFG": str(cfg),
        "FILENAME_PREFIX": filename_prefix,
    }
    
    for key, value in replacements.items():
        workflow_str = workflow_str.replace("{{" + key + "}}", value)
    
    return json.loads(workflow_str)


def generate_mock_image(
    output_path: Path,
    prompt: str,
    seed: int,
) -> Path:
    """Generate a mock placeholder image when ComfyUI is unavailable."""
    # Create a simple placeholder PNG
    # This is a minimal valid PNG file (1x1 pixel, gray)
    png_header = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 pixels
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # 8-bit RGB
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0x60, 0x60, 0x60, 0x00,  # Compressed data
        0x00, 0x00, 0x04, 0x00, 0x01, 0x5C, 0xCD, 0xFF,
        0x69, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
        0x44, 0xAE, 0x42, 0x60, 0x82,
    ])
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(png_header)
    
    return output_path
