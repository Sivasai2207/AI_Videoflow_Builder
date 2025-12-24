"""
Director Generate Task

Background job for generating Director JSON plans using the LLM.
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, create_engine, select

# Import from API
import sys
API_DIR = Path(__file__).resolve().parent.parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from models import Run, RunStatus, DirectorPlanVersion, Project
from models.plan_version import PlanStatus
from schemas.director import (
    DirectorJSON,
    PlanGenerateRequest,
    validate_director_json,
    StylePack,
    Pacing,
    Platform,
    AspectRatioPreset,
)


def get_engine():
    """Create database engine."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    DB_PATH = BASE_DIR / "data" / "db" / "app.sqlite"
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def get_plan_path(project_id: str, run_id: str) -> Path:
    """Get plan directory path."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    plan_path = BASE_DIR / "data" / "projects" / project_id / "runs" / run_id / "plan"
    plan_path.mkdir(parents=True, exist_ok=True)
    return plan_path


def get_logs_path(project_id: str, run_id: str) -> Path:
    """Get logs path for planning."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    logs_path = BASE_DIR / "data" / "projects" / project_id / "runs" / run_id / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    return logs_path / "planning.log"


def write_log(project_id: str, run_id: str, message: str):
    """Write a log message."""
    logs_path = get_logs_path(project_id, run_id)
    timestamp = datetime.utcnow().isoformat()
    with open(logs_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


# ============================================================================
# LLM Integration (synchronous wrapper for worker)
# ============================================================================

import httpx
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def call_ollama(prompt: str, system: str, model: str = DEFAULT_MODEL) -> str:
    """Call Ollama synchronously."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 4096,
        }
    }
    
    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "")


def parse_json_response(response: str) -> dict:
    """Parse JSON from LLM response."""
    # Try direct parsing
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from code block
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            try:
                return json.loads(response[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Try finding JSON boundaries
    start = response.find("{")
    end = response.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not parse JSON from response")


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


def build_user_prompt(request_data: dict) -> tuple[str, int]:
    """Build user prompt and return shot count."""
    pacing = request_data.get("pacing", "medium")
    target_duration = request_data.get("target_duration_sec", 40)
    
    # Calculate shot count
    if pacing == "fast":
        shot_count = 12
    elif pacing == "slow":
        shot_count = 8
    else:
        shot_count = 10
    
    # Dimensions
    aspect_ratio = request_data.get("aspect_ratio", "9:16")
    dimensions = {
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "16:9": (1920, 1080),
    }
    width, height = dimensions.get(aspect_ratio, (1080, 1920))
    
    # Style descriptions
    style_pack = request_data.get("style_pack", "cinematic")
    style_descriptions = {
        "cinematic": "cinematic film look, dramatic lighting, shallow depth of field",
        "anime": "anime art style, vibrant colors, dynamic poses, cel-shaded",
        "photoreal": "photorealistic, highly detailed, natural lighting, DSLR quality",
        "minimal": "minimalist aesthetic, clean lines, simple compositions",
        "pixel": "pixel art style, retro gaming aesthetic, 8-bit look",
        "custom": "custom style as specified",
    }
    
    constraints = request_data.get("constraints", [])
    constraints_text = ""
    if constraints:
        constraints_text = "\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)
    
    prompt = f"""Generate a Director JSON for this video concept:

CONCEPT: {request_data.get("concept", "")}

REQUIREMENTS:
- Platform: {request_data.get("platform", "instagram_reels")}
- Aspect Ratio: {aspect_ratio} ({width}x{height})
- Duration: {target_duration} seconds
- Shots: {shot_count}
- Pacing: {pacing}
- Style: {style_descriptions.get(style_pack, "cinematic")}
{constraints_text}

Return a complete Director JSON with:
- project config
- creative config with style_bible and characters
- safety config
- generation config with seed_policy
- {shot_count} shots with prompts, camera, action_beats

Each shot prompt should be 50-150 words describing the visual for image generation.
Return ONLY valid JSON."""

    return prompt, shot_count


# ============================================================================
# Main Task
# ============================================================================

def generate_director_plan(
    run_id: str,
    project_id: str,
    user_id: str,
    request_data: dict,
):
    """
    Generate a Director JSON plan.
    
    This is the main worker task that:
    1. Updates run status to PLANNING
    2. Calls LLM to generate plan
    3. Validates the JSON schema
    4. Retries once if validation fails
    5. Stores the plan version
    6. Updates run status to PLANNED or FAILED
    """
    engine = get_engine()
    
    with Session(engine) as session:
        # Get run
        run = session.get(Run, UUID(run_id))
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        write_log(project_id, run_id, "Planning started")
        write_log(project_id, run_id, f"Concept: {request_data.get('concept', '')[:100]}...")
        
        try:
            # Build prompt
            user_prompt, shot_count = build_user_prompt(request_data)
            write_log(project_id, run_id, f"Generating {shot_count} shots")
            
            # Update progress
            run.progress = 20
            session.add(run)
            session.commit()
            
            # Check if Ollama is available, use fallback if not
            try:
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(f"{OLLAMA_URL}/api/tags")
                    ollama_available = response.status_code == 200
            except Exception:
                ollama_available = False
            
            if ollama_available:
                write_log(project_id, run_id, "Calling Ollama LLM...")
                raw_response = call_ollama(user_prompt, SYSTEM_PROMPT)
                run.progress = 60
                session.add(run)
                session.commit()
                
                write_log(project_id, run_id, "Parsing LLM response...")
                raw_json = parse_json_response(raw_response)
            else:
                # Fallback: generate mock plan
                write_log(project_id, run_id, "Ollama not available, generating mock plan...")
                raw_json = generate_mock_plan(request_data, shot_count)
            
            # Validate
            run.progress = 70
            session.add(run)
            session.commit()
            
            write_log(project_id, run_id, "Validating plan...")
            director, errors = validate_director_json(raw_json)
            
            # If errors, log them
            if errors:
                write_log(project_id, run_id, f"Validation warnings: {errors}")
            
            if director is None:
                raise ValueError(f"Invalid plan: {errors}")
            
            # Get next version number
            statement = select(DirectorPlanVersion).where(
                DirectorPlanVersion.run_id == UUID(run_id)
            ).order_by(DirectorPlanVersion.version_number.desc())
            existing = session.exec(statement).first()
            next_version = (existing.version_number + 1) if existing else 1
            
            # Create plan version
            director_dict = director.model_dump()
            plan_version = DirectorPlanVersion(
                run_id=UUID(run_id),
                version_number=next_version,
                created_by=UUID(user_id),
                director_json=director_dict,
                status=PlanStatus.DRAFT,
            )
            session.add(plan_version)
            session.flush()  # Get the ID
            
            # Update run
            run.director_json = director_dict
            run.active_plan_version_id = plan_version.id
            run.status = RunStatus.PLANNED
            run.progress = 100
            session.add(run)
            
            session.commit()
            
            # Save to disk
            plan_path = get_plan_path(project_id, run_id)
            with open(plan_path / f"director_v{next_version}.json", "w") as f:
                json.dump(director_dict, f, indent=2)
            with open(plan_path / "director_current.json", "w") as f:
                json.dump(director_dict, f, indent=2)
            
            write_log(project_id, run_id, f"Plan v{next_version} generated successfully")
            write_log(project_id, run_id, f"Generated {len(director.shots)} shots")
            
            return {"status": "success", "version": next_version}
            
        except Exception as e:
            write_log(project_id, run_id, f"Planning failed: {str(e)}")
            run.status = RunStatus.FAILED
            run.progress = 0
            session.add(run)
            session.commit()
            raise


def generate_mock_plan(request_data: dict, shot_count: int) -> dict:
    """Generate a mock plan when Ollama is not available."""
    import random
    
    target_duration = request_data.get("target_duration_sec", 40)
    shot_duration = target_duration // shot_count
    concept = request_data.get("concept", "A cinematic short film")
    style_pack = request_data.get("style_pack", "cinematic")
    
    camera_types = ["close-up", "medium", "wide", "macro"]
    camera_moves = ["static", "push-in", "pan", "tilt"]
    motion_intents = ["low", "medium", "high"]
    
    shots = []
    current_time = 0
    base_seed = random.randint(100000, 999999)
    
    for i in range(shot_count):
        duration = shot_duration
        # Adjust last shot to hit exact duration
        if i == shot_count - 1:
            duration = target_duration - current_time
        
        shots.append({
            "shot_id": f"S{i+1:02d}",
            "duration_sec": duration,
            "timestamp_start_sec": current_time,
            "timestamp_end_sec": current_time + duration,
            "camera": {
                "type": random.choice(camera_types),
                "move": random.choice(camera_moves),
                "notes": ""
            },
            "action_beats": [f"Action beat for shot {i+1}"],
            "prompt": f"Shot {i+1} of {concept}. {style_pack} style, high quality, detailed, professional cinematography.",
            "negative_prompt": "blurry, low quality, distorted, ugly, watermark",
            "motion_intent": random.choice(motion_intents),
            "keyframe_notes": "",
            "seed": base_seed + (i * 17),
            "lock_seed": False,
            "lock_character_style": False,
            "lock_prompt_structure": False,
        })
        current_time += duration
    
    return {
        "schema_version": "1.0",
        "project": {
            "platform": request_data.get("platform", "instagram_reels"),
            "aspect_ratio": request_data.get("aspect_ratio", "9:16"),
            "width": 1080,
            "height": 1920,
            "fps": request_data.get("fps", 30),
            "target_duration_sec": target_duration,
            "shot_count": shot_count,
            "pacing": request_data.get("pacing", "medium"),
        },
        "creative": {
            "title": concept[:50],
            "logline": concept,
            "genre": "general",
            "style_pack": style_pack,
            "style_bible": {
                "visual_keywords": [style_pack, "cinematic", "professional"],
                "lighting": "natural lighting with dramatic shadows",
                "color_palette": "rich, vibrant colors",
                "lens_and_camera": "35mm equivalent, shallow depth of field",
                "composition_rules": ["rule of thirds", "leading lines"],
                "do_not_do": ["overexposed", "dutch angle"]
            },
            "characters": [],
            "locations": ["various locations as needed"]
        },
        "safety": {
            "platform_safe_mode": True,
            "avoid": ["nudity", "hate", "extreme_gore", "illegal"],
            "notes": ""
        },
        "generation": {
            "seed_policy": {
                "base_seed": base_seed,
                "per_shot_offset": 17
            },
            "consistency": {
                "use_hero_frame": True,
                "use_ip_adapter": True,
                "reference_strategy": "hero_only"
            },
            "negative_prompt_global": "blurry, low quality, distorted, ugly, watermark, text"
        },
        "shots": shots
    }
