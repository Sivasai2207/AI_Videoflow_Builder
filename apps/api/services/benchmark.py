"""
Benchmark Service

Performance benchmarking and profile generation.
"""
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID

from sqlmodel import Session, select

from models.system_model import PerformanceProfile, SystemSettings


def get_machine_info() -> Dict[str, Any]:
    """Get machine information."""
    info = {
        "machine_name": platform.node(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine_chip": None,
        "machine_ram_gb": None,
    }
    
    # Try to get Apple Silicon info on macOS
    if platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                info["machine_chip"] = result.stdout.strip()
            
            # Get RAM
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                ram_bytes = int(result.stdout.strip())
                info["machine_ram_gb"] = ram_bytes // (1024 ** 3)
        except Exception:
            pass
    
    return info


def run_image_benchmark(
    width: int = 768,
    height: int = 1344,
    steps: int = 6,
) -> Dict[str, Any]:
    """Run image generation benchmark."""
    from services.renderer import get_renderer, RenderRequest
    from models.system_model import RendererTarget
    
    renderer = get_renderer(RendererTarget.LOCAL_COMFYUI)
    
    # Check if renderer is available
    if not renderer.check_health():
        return {
            "success": False,
            "error": "ComfyUI not available",
            "duration_seconds": None,
        }
    
    # Create temp output dir
    output_dir = Path("/tmp/benchmark_images")
    output_dir.mkdir(exist_ok=True)
    
    request = RenderRequest(
        workflow_id="keyframe_base",
        inputs={
            "prompt": "A beautiful mountain landscape at sunset, cinematic lighting",
            "negative_prompt": "blurry, low quality",
            "seed": 12345,
            "filename_prefix": "benchmark",
            "params": {
                "width": width,
                "height": height,
                "steps": steps,
                "cfg": 4.0,
            },
        },
        output_dir=output_dir,
    )
    
    start_time = time.time()
    result = renderer.render_image(request)
    duration = time.time() - start_time
    
    return {
        "success": result.success,
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "steps": steps,
        "error": result.error,
    }


def run_video_benchmark(
    duration_sec: float = 2.0,
    clip_type: str = "preview",
) -> Dict[str, Any]:
    """Run video generation benchmark."""
    from services.video import create_mock_video
    
    output_dir = Path("/tmp/benchmark_videos")
    output_dir.mkdir(exist_ok=True)
    
    output_path = output_dir / f"benchmark_{clip_type}.mp4"
    
    start_time = time.time()
    success = create_mock_video(str(output_path), duration_sec)
    render_duration = time.time() - start_time
    
    return {
        "success": success,
        "duration_seconds": render_duration,
        "clip_duration_sec": duration_sec,
        "clip_type": clip_type,
    }


def run_full_benchmark(session: Session) -> PerformanceProfile:
    """Run full benchmark suite and create profile."""
    machine_info = get_machine_info()
    
    # Run benchmarks
    image_result = run_image_benchmark()
    preview_result = run_video_benchmark(duration_sec=2.0, clip_type="preview")
    final_result = run_video_benchmark(duration_sec=4.0, clip_type="final")
    
    # Calculate safe defaults based on results
    safe_defaults = calculate_safe_defaults(
        image_result, preview_result, final_result, machine_info
    )
    
    # Create profile
    profile = PerformanceProfile(
        machine_name=machine_info["machine_name"],
        machine_chip=machine_info.get("machine_chip"),
        machine_ram_gb=machine_info.get("machine_ram_gb"),
        tested_at=datetime.utcnow(),
        image_test_seconds=image_result.get("duration_seconds"),
        preview_video_test_seconds=preview_result.get("duration_seconds"),
        final_video_test_seconds=final_result.get("duration_seconds"),
        safe_defaults_json=safe_defaults,
        is_active=True,
    )
    
    # Deactivate existing profiles
    existing = session.exec(select(PerformanceProfile).where(PerformanceProfile.is_active == True)).all()
    for p in existing:
        p.is_active = False
        session.add(p)
    
    session.add(profile)
    session.commit()
    session.refresh(profile)
    
    return profile


def calculate_safe_defaults(
    image_result: Dict,
    preview_result: Dict,
    final_result: Dict,
    machine_info: Dict,
) -> Dict[str, Any]:
    """Calculate safe defaults based on benchmark results."""
    defaults = {
        "keyframe_width": 768,
        "keyframe_height": 1344,
        "keyframe_steps": 6,
        "keyframe_cfg": 4.0,
        "max_parallel_jobs": 1,
        "preview_duration_sec": 2.0,
        "final_clip_duration_sec": 4.0,
    }
    
    ram_gb = machine_info.get("machine_ram_gb", 8)
    
    # Adjust based on RAM
    if ram_gb >= 32:
        defaults["keyframe_steps"] = 8
        defaults["max_parallel_jobs"] = 2
    elif ram_gb >= 16:
        defaults["keyframe_steps"] = 6
        defaults["max_parallel_jobs"] = 1
    else:
        defaults["keyframe_steps"] = 4
        defaults["keyframe_width"] = 512
        defaults["keyframe_height"] = 896
    
    # Adjust based on image render time
    image_time = image_result.get("duration_seconds")
    if image_time:
        if image_time > 30:
            # Slow machine, reduce quality
            defaults["keyframe_steps"] = max(4, defaults["keyframe_steps"] - 2)
        elif image_time < 10:
            # Fast machine, can increase quality
            defaults["keyframe_steps"] = min(10, defaults["keyframe_steps"] + 2)
    
    return defaults


def get_active_profile(session: Session) -> Optional[PerformanceProfile]:
    """Get the currently active performance profile."""
    return session.exec(
        select(PerformanceProfile).where(PerformanceProfile.is_active == True)
    ).first()


def apply_profile_defaults(session: Session, profile_id: UUID) -> Dict[str, Any]:
    """Apply a profile's safe defaults to system settings."""
    profile = session.get(PerformanceProfile, profile_id)
    if not profile:
        return {"success": False, "error": "Profile not found"}
    
    # Deactivate all, activate this one
    all_profiles = session.exec(select(PerformanceProfile)).all()
    for p in all_profiles:
        p.is_active = (p.id == profile_id)
        session.add(p)
    
    # Update system settings
    settings = session.get(SystemSettings, 1)
    if settings:
        settings.active_performance_profile_id = profile_id
        session.add(settings)
    
    session.commit()
    
    return {
        "success": True,
        "profile_id": str(profile_id),
        "defaults": profile.safe_defaults_json,
    }
