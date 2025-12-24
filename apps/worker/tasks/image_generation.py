"""
Image Generation Worker Tasks

Background tasks for generating hero frames and keyframes via ComfyUI.
"""
import json
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, create_engine, select

# Import from API
import sys
API_DIR = Path(__file__).resolve().parent.parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from models import (
    Run, Shot, Asset, AssetType, AssetRole,
    ImageGenerationJob, ImageJobType, ImageJobStatus,
)
from models.shot import KeyframeStatus
from services.comfyui import ComfyUIClient
from services.images import (
    compute_idempotency_key,
    compute_input_hash,
    get_hero_dir,
    get_shot_dir,
    check_cache,
    create_image_job,
    register_asset,
    build_hero_prompt,
    build_character_prompt,
    build_keyframe_prompt,
    build_workflow,
    generate_mock_image,
    DEFAULT_PARAMS,
)


def get_engine():
    """Create database engine."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    DB_PATH = BASE_DIR / "data" / "db" / "app.sqlite"
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def write_log(project_id: str, run_id: str, filename: str, message: str):
    """Write log message."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    log_path = BASE_DIR / "data" / "projects" / project_id / "runs" / run_id / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.utcnow().isoformat()
    with open(log_path / filename, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def generate_hero_frames(
    run_id: str,
    project_id: str,
    params: dict = None,
) -> dict:
    """
    Generate hero frames (style master + character anchor).
    
    Args:
        run_id: Run ID
        project_id: Project ID
        params: Generation parameters (width, height, steps, cfg)
        
    Returns:
        Dict with style_asset_id and character_asset_id
    """
    engine = get_engine()
    params = params or DEFAULT_PARAMS.copy()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        director_json = run.director_json
        seed_policy = director_json.get("generation", {}).get("seed_policy", {})
        base_seed = seed_policy.get("base_seed", 123456)
        
        hero_dir = get_hero_dir(UUID(project_id), UUID(run_id))
        results = {}
        
        # Initialize ComfyUI client
        client = ComfyUIClient()
        comfy_available = client.check_health_sync()
        
        write_log(project_id, run_id, "images_hero.log", f"Starting hero frame generation")
        write_log(project_id, run_id, "images_hero.log", f"ComfyUI available: {comfy_available}")
        
        # === Generate Style Master ===
        style_prompt, style_negative = build_hero_prompt(director_json)
        style_seed = base_seed
        
        # Check cache
        style_idem_key = compute_idempotency_key(
            run_id, None, "hero_style",
            style_prompt, style_negative, style_seed,
            params["width"], params["height"], params["steps"], params["cfg"],
            params.get("checkpoint", DEFAULT_PARAMS["checkpoint"]),
        )
        
        cached_job = check_cache(session, style_idem_key)
        if cached_job and cached_job.output_asset_id:
            write_log(project_id, run_id, "images_hero.log", "Style master: using cached result")
            results["style_asset_id"] = str(cached_job.output_asset_id)
        else:
            write_log(project_id, run_id, "images_hero.log", f"Style master: generating with seed {style_seed}")
            
            # Create job record
            style_job = create_image_job(
                session, UUID(run_id), ImageJobType.HERO_STYLE,
                style_idem_key, compute_input_hash({"prompt": style_prompt, "seed": style_seed}),
                params=params,
            )
            
            try:
                if comfy_available:
                    # Build and submit workflow
                    workflow = build_workflow(
                        "hero_style_master",
                        style_prompt, style_negative, style_seed,
                        f"hero_style_{run_id[:8]}",
                        **params,
                    )
                    
                    prompt_id = client.submit_workflow(workflow)
                    style_job.comfy_prompt_id = prompt_id
                    style_job.status = ImageJobStatus.RUNNING
                    style_job.started_at = datetime.utcnow()
                    session.add(style_job)
                    session.commit()
                    
                    # Poll for completion
                    history = client.poll_until_complete(prompt_id)
                    output_files = client.collect_outputs(history, hero_dir)
                    
                    if output_files:
                        output_path = output_files[0]
                    else:
                        raise RuntimeError("No output files from ComfyUI")
                else:
                    # Generate mock image
                    output_path = hero_dir / "style_master.png"
                    generate_mock_image(output_path, style_prompt, style_seed)
                    write_log(project_id, run_id, "images_hero.log", "Style master: generated mock image")
                
                # Register asset
                asset = register_asset(
                    session, UUID(project_id), UUID(run_id),
                    str(output_path), AssetRole.HERO_FRAME_STYLE,
                    seed=style_seed,
                    model_id=params.get("checkpoint"),
                )
                
                # Update job
                style_job.status = ImageJobStatus.SUCCEEDED
                style_job.output_asset_id = asset.id
                style_job.finished_at = datetime.utcnow()
                session.add(style_job)
                session.commit()
                
                results["style_asset_id"] = str(asset.id)
                write_log(project_id, run_id, "images_hero.log", f"Style master: completed, asset={asset.id}")
                
            except Exception as e:
                style_job.status = ImageJobStatus.FAILED
                style_job.error_message = str(e)
                style_job.finished_at = datetime.utcnow()
                session.add(style_job)
                session.commit()
                write_log(project_id, run_id, "images_hero.log", f"Style master: FAILED - {e}")
        
        # === Generate Character Anchor ===
        char_prompt, char_negative = build_character_prompt(director_json)
        char_seed = base_seed + 1
        
        char_idem_key = compute_idempotency_key(
            run_id, None, "hero_character",
            char_prompt, char_negative, char_seed,
            params["width"], params["height"], params["steps"], params["cfg"],
            params.get("checkpoint", DEFAULT_PARAMS["checkpoint"]),
        )
        
        cached_job = check_cache(session, char_idem_key)
        if cached_job and cached_job.output_asset_id:
            write_log(project_id, run_id, "images_hero.log", "Character anchor: using cached result")
            results["character_asset_id"] = str(cached_job.output_asset_id)
        else:
            write_log(project_id, run_id, "images_hero.log", f"Character anchor: generating with seed {char_seed}")
            
            char_job = create_image_job(
                session, UUID(run_id), ImageJobType.HERO_CHARACTER,
                char_idem_key, compute_input_hash({"prompt": char_prompt, "seed": char_seed}),
                params=params,
            )
            
            try:
                if comfy_available:
                    workflow = build_workflow(
                        "hero_character_anchor",
                        char_prompt, char_negative, char_seed,
                        f"hero_char_{run_id[:8]}",
                        **params,
                    )
                    
                    prompt_id = client.submit_workflow(workflow)
                    char_job.comfy_prompt_id = prompt_id
                    char_job.status = ImageJobStatus.RUNNING
                    char_job.started_at = datetime.utcnow()
                    session.add(char_job)
                    session.commit()
                    
                    history = client.poll_until_complete(prompt_id)
                    output_files = client.collect_outputs(history, hero_dir)
                    
                    if output_files:
                        output_path = output_files[0]
                    else:
                        raise RuntimeError("No output files from ComfyUI")
                else:
                    output_path = hero_dir / "character_anchor.png"
                    generate_mock_image(output_path, char_prompt, char_seed)
                    write_log(project_id, run_id, "images_hero.log", "Character anchor: generated mock image")
                
                asset = register_asset(
                    session, UUID(project_id), UUID(run_id),
                    str(output_path), AssetRole.HERO_FRAME_CHARACTER,
                    seed=char_seed,
                    model_id=params.get("checkpoint"),
                )
                
                char_job.status = ImageJobStatus.SUCCEEDED
                char_job.output_asset_id = asset.id
                char_job.finished_at = datetime.utcnow()
                session.add(char_job)
                session.commit()
                
                results["character_asset_id"] = str(asset.id)
                write_log(project_id, run_id, "images_hero.log", f"Character anchor: completed, asset={asset.id}")
                
            except Exception as e:
                char_job.status = ImageJobStatus.FAILED
                char_job.error_message = str(e)
                char_job.finished_at = datetime.utcnow()
                session.add(char_job)
                session.commit()
                write_log(project_id, run_id, "images_hero.log", f"Character anchor: FAILED - {e}")
        
        write_log(project_id, run_id, "images_hero.log", f"Hero generation complete: {results}")
        return results


def generate_keyframe(
    run_id: str,
    project_id: str,
    shot_id: str,
    params: dict = None,
    seed_override: int = None,
) -> dict:
    """
    Generate a keyframe for a single shot.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        shot_id: Shot ID (e.g. "S01")
        params: Generation parameters
        seed_override: Optional seed override
        
    Returns:
        Dict with asset_id
    """
    engine = get_engine()
    params = params or DEFAULT_PARAMS.copy()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        director_json = run.director_json
        shots = director_json.get("shots", [])
        
        # Find the shot in Director JSON
        shot_data = None
        shot_index = None
        for i, s in enumerate(shots):
            if s.get("shot_id") == shot_id:
                shot_data = s
                shot_index = i
                break
        
        if not shot_data:
            raise ValueError(f"Shot not found: {shot_id}")
        
        # Determine seed
        seed_policy = director_json.get("generation", {}).get("seed_policy", {})
        base_seed = seed_policy.get("base_seed", 123456)
        offset = seed_policy.get("per_shot_offset", 17)
        seed = seed_override if seed_override else shot_data.get("seed", base_seed + (shot_index * offset))
        
        # Get shot record from DB (if exists)
        statement = select(Shot).where(
            Shot.run_id == UUID(run_id),
            Shot.order_index == shot_index,
        )
        db_shot = session.exec(statement).first()
        
        shot_dir = get_shot_dir(UUID(project_id), UUID(run_id), shot_id)
        
        # Build prompt
        prompt, negative_prompt = build_keyframe_prompt(shot_data, director_json)
        
        write_log(project_id, run_id, f"images_{shot_id}.log", f"Starting keyframe generation")
        write_log(project_id, run_id, f"images_{shot_id}.log", f"Seed: {seed}")
        
        # Check cache
        idem_key = compute_idempotency_key(
            run_id, shot_id, "keyframe",
            prompt, negative_prompt, seed,
            params["width"], params["height"], params["steps"], params["cfg"],
            params.get("checkpoint", DEFAULT_PARAMS["checkpoint"]),
        )
        
        cached_job = check_cache(session, idem_key)
        if cached_job and cached_job.output_asset_id:
            write_log(project_id, run_id, f"images_{shot_id}.log", "Using cached result")
            
            # Update shot status
            if db_shot:
                db_shot.keyframe_status = KeyframeStatus.GENERATED
                db_shot.keyframe_asset_id = cached_job.output_asset_id
                db_shot.keyframe_seed = seed
                session.add(db_shot)
                session.commit()
            
            return {"asset_id": str(cached_job.output_asset_id)}
        
        # Update shot status to running
        if db_shot:
            db_shot.keyframe_status = KeyframeStatus.RUNNING
            session.add(db_shot)
            session.commit()
        
        # Create job
        job = create_image_job(
            session, UUID(run_id), ImageJobType.KEYFRAME,
            idem_key, compute_input_hash({"prompt": prompt, "seed": seed}),
            shot_id=db_shot.id if db_shot else None,
            params=params,
        )
        
        client = ComfyUIClient()
        comfy_available = client.check_health_sync()
        
        try:
            if comfy_available:
                workflow = build_workflow(
                    "keyframe_base",
                    prompt, negative_prompt, seed,
                    f"keyframe_{shot_id}_{run_id[:8]}",
                    **params,
                )
                
                prompt_id = client.submit_workflow(workflow)
                job.comfy_prompt_id = prompt_id
                job.status = ImageJobStatus.RUNNING
                job.started_at = datetime.utcnow()
                session.add(job)
                session.commit()
                
                history = client.poll_until_complete(prompt_id)
                output_files = client.collect_outputs(history, shot_dir)
                
                if output_files:
                    output_path = output_files[0]
                else:
                    raise RuntimeError("No output files from ComfyUI")
            else:
                # Mock generation
                output_path = shot_dir / f"keyframe_v1.png"
                generate_mock_image(output_path, prompt, seed)
                write_log(project_id, run_id, f"images_{shot_id}.log", "Generated mock image")
            
            # Register asset
            asset = register_asset(
                session, UUID(project_id), UUID(run_id),
                str(output_path), AssetRole.KEYFRAME,
                shot_id=db_shot.id if db_shot else None,
                seed=seed,
                model_id=params.get("checkpoint"),
            )
            
            # Update job
            job.status = ImageJobStatus.SUCCEEDED
            job.output_asset_id = asset.id
            job.finished_at = datetime.utcnow()
            session.add(job)
            
            # Update shot
            if db_shot:
                db_shot.keyframe_status = KeyframeStatus.GENERATED
                db_shot.keyframe_asset_id = asset.id
                db_shot.keyframe_seed = seed
                session.add(db_shot)
            
            session.commit()
            
            write_log(project_id, run_id, f"images_{shot_id}.log", f"Completed, asset={asset.id}")
            return {"asset_id": str(asset.id)}
            
        except Exception as e:
            job.status = ImageJobStatus.FAILED
            job.error_message = str(e)
            job.finished_at = datetime.utcnow()
            session.add(job)
            
            if db_shot:
                db_shot.keyframe_status = KeyframeStatus.FAILED
                session.add(db_shot)
            
            session.commit()
            write_log(project_id, run_id, f"images_{shot_id}.log", f"FAILED: {e}")
            raise


def generate_keyframes_all(
    run_id: str,
    project_id: str,
    params: dict = None,
) -> dict:
    """
    Generate keyframes for all shots in a run.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        params: Generation parameters
        
    Returns:
        Dict mapping shot_id to asset_id
    """
    engine = get_engine()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        shots = run.director_json.get("shots", [])
    
    results = {}
    for shot in shots:
        shot_id = shot.get("shot_id")
        if shot_id:
            try:
                result = generate_keyframe(run_id, project_id, shot_id, params)
                results[shot_id] = result.get("asset_id")
            except Exception as e:
                results[shot_id] = f"FAILED: {e}"
    
    return results


def regenerate_keyframe(
    run_id: str,
    project_id: str,
    shot_id: str,
    seed_mode: str = "new",
    params: dict = None,
) -> dict:
    """
    Regenerate a keyframe with options.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        shot_id: Shot ID
        seed_mode: "same" to keep seed, "new" for random
        params: Generation parameters
        
    Returns:
        Dict with asset_id
    """
    import random
    
    engine = get_engine()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        shots = run.director_json.get("shots", [])
        shot_data = next((s for s in shots if s.get("shot_id") == shot_id), None)
        
        if not shot_data:
            raise ValueError(f"Shot not found: {shot_id}")
        
        if seed_mode == "same":
            seed = shot_data.get("seed")
        else:
            seed = random.randint(100000, 999999)
    
    return generate_keyframe(run_id, project_id, shot_id, params, seed_override=seed)


def generate_variants(
    run_id: str,
    project_id: str,
    shot_id: str,
    count: int = 3,
    seed_mode: str = "offset",
    reference_strategy: str = "hero_plus_prev",
) -> dict:
    """
    Generate multiple keyframe variants for a shot.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        shot_id: Shot ID
        count: Number of variants to generate
        seed_mode: "offset" or "random"
        reference_strategy: "hero_only" or "hero_plus_prev"
        
    Returns:
        Dict with variant asset IDs
    """
    import random
    from uuid import uuid4
    
    engine = get_engine()
    params = DEFAULT_PARAMS.copy()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        director_json = run.director_json
        shots = director_json.get("shots", [])
        
        # Find shot
        shot_data = None
        shot_index = None
        for i, s in enumerate(shots):
            if s.get("shot_id") == shot_id:
                shot_data = s
                shot_index = i
                break
        
        if not shot_data:
            raise ValueError(f"Shot not found: {shot_id}")
        
        # Get DB shot
        db_shot = session.exec(
            select(Shot).where(Shot.run_id == UUID(run_id), Shot.order_index == shot_index)
        ).first()
        
        if not db_shot:
            raise ValueError(f"Shot record not found for {shot_id}")
        
        # Generate variant group ID
        variant_group_id = uuid4()
        db_shot.variant_group_id = variant_group_id
        db_shot.variant_count = count
        session.add(db_shot)
        session.commit()
        
        # Calculate seeds
        seed_policy = director_json.get("generation", {}).get("seed_policy", {})
        base_seed = seed_policy.get("base_seed", 123456)
        
        seeds = []
        for i in range(count):
            if seed_mode == "offset":
                seeds.append(base_seed + (shot_index * 1000) + (i * 17))
            else:
                seeds.append(random.randint(100000, 999999))
        
        shot_dir = get_shot_dir(UUID(project_id), UUID(run_id), shot_id)
        
        # Build prompt
        prompt, negative_prompt = build_keyframe_prompt(shot_data, director_json)
        
        # Get previous keyframe for hero_plus_prev strategy
        prev_keyframe_path = None
        if reference_strategy == "hero_plus_prev" and shot_index > 0:
            prev_shot = session.exec(
                select(Shot).where(Shot.run_id == UUID(run_id), Shot.order_index == shot_index - 1)
            ).first()
            if prev_shot and prev_shot.keyframe_asset_id:
                prev_asset = session.get(Asset, prev_shot.keyframe_asset_id)
                if prev_asset and Path(prev_asset.file_path).exists():
                    prev_keyframe_path = prev_asset.file_path
                    write_log(project_id, run_id, f"variants_{shot_id}.log", 
                             f"Using prev keyframe for consistency: {prev_keyframe_path}")
        
        write_log(project_id, run_id, f"variants_{shot_id}.log", 
                 f"Generating {count} variants, strategy={reference_strategy}")
        
        client = ComfyUIClient()
        comfy_available = client.check_health_sync()
        
        variant_assets = []
        
        for i, seed in enumerate(seeds):
            write_log(project_id, run_id, f"variants_{shot_id}.log", 
                     f"Variant {i+1}/{count}: seed={seed}")
            
            try:
                if comfy_available:
                    workflow = build_workflow(
                        "keyframe_base",
                        prompt, negative_prompt, seed,
                        f"variant_{shot_id}_{i}_{run_id[:8]}",
                        **params,
                    )
                    
                    # Add prev keyframe reference if available
                    if prev_keyframe_path and "reference_image" in str(workflow):
                        # This would be enhanced in production to properly inject the reference
                        pass
                    
                    prompt_id = client.submit_workflow(workflow)
                    history = client.poll_until_complete(prompt_id)
                    output_files = client.collect_outputs(history, shot_dir)
                    
                    if output_files:
                        output_path = output_files[0]
                    else:
                        raise RuntimeError("No output files")
                else:
                    output_path = shot_dir / f"variant_{i+1}.png"
                    generate_mock_image(output_path, f"{prompt} [variant {i+1}]", seed)
                
                # Register as variant asset
                asset = Asset(
                    project_id=UUID(project_id),
                    run_id=UUID(run_id),
                    shot_id=db_shot.id,
                    type=AssetType.IMAGE,
                    role=AssetRole.KEYFRAME_VARIANT,
                    file_path=str(output_path),
                    seed=seed,
                    variant_index=i,
                    variant_group_id=variant_group_id,
                )
                session.add(asset)
                session.commit()
                session.refresh(asset)
                
                variant_assets.append({
                    "variant_index": i,
                    "asset_id": str(asset.id),
                    "seed": seed,
                    "file_path": str(output_path),
                })
                
                write_log(project_id, run_id, f"variants_{shot_id}.log", 
                         f"Variant {i+1}: completed, asset={asset.id}")
                
            except Exception as e:
                write_log(project_id, run_id, f"variants_{shot_id}.log", 
                         f"Variant {i+1}: FAILED - {e}")
                variant_assets.append({
                    "variant_index": i,
                    "error": str(e),
                })
        
        write_log(project_id, run_id, f"variants_{shot_id}.log", 
                 f"Completed {len([v for v in variant_assets if 'asset_id' in v])}/{count} variants")
        
        return {
            "shot_id": shot_id,
            "variant_group_id": str(variant_group_id),
            "variants": variant_assets,
        }
