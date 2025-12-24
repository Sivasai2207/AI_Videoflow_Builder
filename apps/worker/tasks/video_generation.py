"""
Video Generation Worker Tasks

Background tasks for generating videos from keyframes.
"""
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, create_engine, select

# Import from API
import sys
API_DIR = Path(__file__).resolve().parent.parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from models import (
    Run, Shot, Asset, AssetRole,
    VideoClip, ClipType, VideoClipStatus,
    AudioTrack, TrackType,
    FinalExport, ExportPreset, ExportStatus,
)
from models.shot import KeyframeStatus
from services.video import (
    generate_video_from_keyframe,
    stitch_video_clips,
    add_audio_to_video,
    mix_audio_tracks,
    get_shot_video_path,
    get_stitched_video_path,
    get_final_video_path,
    get_video_dir,
)
from services.audio import (
    generate_voiceover,
    build_voiceover_script,
    get_audio_dir,
)


def get_engine():
    """Create database engine."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    DB_PATH = BASE_DIR / "data" / "db" / "app.sqlite"
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def write_log(project_id: str, run_id: str, message: str):
    """Write log message."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    log_path = BASE_DIR / "data" / "projects" / project_id / "runs" / run_id / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.utcnow().isoformat()
    with open(log_path / "video.log", "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def generate_shot_video(
    run_id: str,
    project_id: str,
    shot_id: str,
    clip_type: str = "preview",
) -> dict:
    """
    Generate a video clip for a single shot.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        shot_id: Shot ID (e.g., "S01")
        clip_type: "preview" or "final"
        
    Returns:
        Dict with video_clip_id and file_path
    """
    engine = get_engine()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        director_json = run.director_json
        shots = director_json.get("shots", [])
        
        # Find shot in director JSON
        shot_data = None
        shot_index = None
        for i, s in enumerate(shots):
            if s.get("shot_id") == shot_id:
                shot_data = s
                shot_index = i
                break
        
        if not shot_data:
            raise ValueError(f"Shot not found: {shot_id}")
        
        duration_sec = shot_data.get("duration_sec", 4)
        motion_intent = shot_data.get("motion_intent", "medium")
        
        # Map motion intent to motion type
        motion_map = {
            "low": "static",
            "medium": "zoom_in",
            "high": "zoom_in",
        }
        motion_type = motion_map.get(motion_intent, "zoom_in")
        motion_intensity = {"low": 0.05, "medium": 0.1, "high": 0.2}.get(motion_intent, 0.1)
        
        # Get keyframe asset
        statement = select(Shot).where(
            Shot.run_id == UUID(run_id),
            Shot.order_index == shot_index,
        )
        db_shot = session.exec(statement).first()
        
        keyframe_path = None
        if db_shot and db_shot.keyframe_asset_id:
            asset = session.get(Asset, db_shot.keyframe_asset_id)
            if asset:
                keyframe_path = asset.file_path
        
        if not keyframe_path or not Path(keyframe_path).exists():
            # Use placeholder if no keyframe
            write_log(project_id, run_id, f"No keyframe for {shot_id}, using placeholder")
            # Create a placeholder video
            output_path = get_shot_video_path(UUID(project_id), UUID(run_id), shot_id, clip_type)
            from services.video import create_mock_video
            create_mock_video(str(output_path), duration_sec)
        else:
            output_path = get_shot_video_path(UUID(project_id), UUID(run_id), shot_id, clip_type)
            
            write_log(project_id, run_id, f"Generating video for {shot_id}: {duration_sec}s, {motion_type}")
            
            success = generate_video_from_keyframe(
                keyframe_path=keyframe_path,
                output_path=str(output_path),
                duration_sec=duration_sec,
                fps=30,
                motion_type=motion_type,
                motion_intensity=motion_intensity,
            )
            
            if not success:
                raise RuntimeError(f"Failed to generate video for {shot_id}")
        
        # Create video clip record
        video_clip = VideoClip(
            run_id=UUID(run_id),
            shot_id=db_shot.id if db_shot else None,
            clip_type=ClipType.PREVIEW if clip_type == "preview" else ClipType.FINAL,
            status=VideoClipStatus.SUCCEEDED,
            file_path=str(output_path),
            duration_sec=duration_sec,
            keyframe_asset_id=db_shot.keyframe_asset_id if db_shot else None,
            finished_at=datetime.utcnow(),
        )
        session.add(video_clip)
        session.commit()
        session.refresh(video_clip)
        
        write_log(project_id, run_id, f"Video generated for {shot_id}: {output_path}")
        
        return {
            "video_clip_id": str(video_clip.id),
            "file_path": str(output_path),
        }


def generate_all_videos(
    run_id: str,
    project_id: str,
    clip_type: str = "preview",
) -> dict:
    """
    Generate videos for all shots in a run.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        clip_type: "preview" or "final"
        
    Returns:
        Dict mapping shot_id to video_clip_id
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
                result = generate_shot_video(run_id, project_id, shot_id, clip_type)
                results[shot_id] = result.get("video_clip_id")
            except Exception as e:
                results[shot_id] = f"FAILED: {e}"
                write_log(project_id, run_id, f"Failed to generate video for {shot_id}: {e}")
    
    return results


def stitch_final_video(
    run_id: str,
    project_id: str,
) -> dict:
    """
    Stitch all shot videos into a single video.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        
    Returns:
        Dict with video_clip_id and file_path
    """
    engine = get_engine()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        shots = run.director_json.get("shots", [])
        
        # Get all video clips in order
        clip_paths = []
        for i, shot in enumerate(shots):
            shot_id = shot.get("shot_id")
            video_path = get_shot_video_path(UUID(project_id), UUID(run_id), shot_id, "preview")
            if video_path.exists():
                clip_paths.append(str(video_path))
        
        if not clip_paths:
            raise ValueError("No video clips found to stitch")
        
        output_path = get_stitched_video_path(UUID(project_id), UUID(run_id))
        
        write_log(project_id, run_id, f"Stitching {len(clip_paths)} clips")
        
        success = stitch_video_clips(clip_paths, str(output_path))
        
        if not success:
            raise RuntimeError("Failed to stitch video clips")
        
        # Calculate total duration
        total_duration = sum(s.get("duration_sec", 4) for s in shots)
        
        # Create video clip record
        video_clip = VideoClip(
            run_id=UUID(run_id),
            shot_id=None,
            clip_type=ClipType.STITCHED,
            status=VideoClipStatus.SUCCEEDED,
            file_path=str(output_path),
            duration_sec=total_duration,
            finished_at=datetime.utcnow(),
        )
        session.add(video_clip)
        session.commit()
        session.refresh(video_clip)
        
        write_log(project_id, run_id, f"Stitched video created: {output_path}")
        
        return {
            "video_clip_id": str(video_clip.id),
            "file_path": str(output_path),
        }


def generate_voiceover_track(
    run_id: str,
    project_id: str,
    script: str = None,
) -> dict:
    """
    Generate voiceover audio for a run.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        script: Optional script text (auto-generated if not provided)
        
    Returns:
        Dict with audio_track_id and file_path
    """
    engine = get_engine()
    
    with Session(engine) as session:
        run = session.get(Run, UUID(run_id))
        if not run or not run.director_json:
            raise ValueError(f"Run not found or no plan: {run_id}")
        
        # Build script if not provided
        if not script:
            script = build_voiceover_script(run.director_json)
        
        audio_dir = get_audio_dir(UUID(project_id), UUID(run_id))
        output_path = audio_dir / "voiceover.mp3"
        
        write_log(project_id, run_id, f"Generating voiceover: {len(script)} chars")
        
        success = generate_voiceover(script, str(output_path))
        
        if not success:
            raise RuntimeError("Failed to generate voiceover")
        
        # Estimate duration
        word_count = len(script.split())
        duration_sec = max(5.0, word_count / 2.5)
        
        # Create audio track record
        audio_track = AudioTrack(
            run_id=UUID(run_id),
            track_type=TrackType.VOICEOVER,
            file_path=str(output_path),
            duration_sec=duration_sec,
            script_text=script,
        )
        session.add(audio_track)
        session.commit()
        session.refresh(audio_track)
        
        write_log(project_id, run_id, f"Voiceover generated: {output_path}")
        
        return {
            "audio_track_id": str(audio_track.id),
            "file_path": str(output_path),
        }


def create_final_with_audio(
    run_id: str,
    project_id: str,
    include_voiceover: bool = True,
    include_music: bool = False,
    voiceover_volume: float = 1.0,
    music_volume: float = 0.3,
) -> dict:
    """
    Create final video with audio.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        include_voiceover: Include voiceover track
        include_music: Include music track
        voiceover_volume: Voiceover volume level
        music_volume: Music volume level
        
    Returns:
        Dict with file_path
    """
    engine = get_engine()
    
    with Session(engine) as session:
        # Get stitched video
        stitched_path = get_stitched_video_path(UUID(project_id), UUID(run_id))
        if not stitched_path.exists():
            raise ValueError("No stitched video found. Stitch first.")
        
        audio_dir = get_audio_dir(UUID(project_id), UUID(run_id))
        video_dir = get_video_dir(UUID(project_id), UUID(run_id))
        
        # Get audio tracks
        voiceover_path = None
        music_path = None
        
        if include_voiceover:
            vo_track = session.exec(
                select(AudioTrack).where(
                    AudioTrack.run_id == UUID(run_id),
                    AudioTrack.track_type == TrackType.VOICEOVER,
                )
            ).first()
            if vo_track and Path(vo_track.file_path).exists():
                voiceover_path = vo_track.file_path
        
        if include_music:
            music_track = session.exec(
                select(AudioTrack).where(
                    AudioTrack.run_id == UUID(run_id),
                    AudioTrack.track_type == TrackType.MUSIC,
                )
            ).first()
            if music_track and Path(music_track.file_path).exists():
                music_path = music_track.file_path
        
        # Mix audio if needed
        if voiceover_path or music_path:
            mixed_audio_path = audio_dir / "mixed.mp3"
            mix_audio_tracks(
                voiceover_path,
                music_path,
                str(mixed_audio_path),
                voiceover_volume,
                music_volume,
            )
            
            # Mux video with audio
            final_path = get_final_video_path(UUID(project_id), UUID(run_id))
            success = add_audio_to_video(
                str(stitched_path),
                str(mixed_audio_path),
                str(final_path),
            )
            
            if not success:
                raise RuntimeError("Failed to add audio to video")
        else:
            # No audio, just copy stitched
            import shutil
            final_path = get_final_video_path(UUID(project_id), UUID(run_id))
            shutil.copy2(stitched_path, final_path)
        
        write_log(project_id, run_id, f"Final video created: {final_path}")
        
        return {
            "file_path": str(final_path),
        }


def export_video(
    run_id: str,
    project_id: str,
    preset: str = "instagram_reels",
) -> dict:
    """
    Export final video with platform-specific settings.
    
    Args:
        run_id: Run ID
        project_id: Project ID
        preset: Export preset name
        
    Returns:
        Dict with export_id and file_path
    """
    import subprocess
    
    engine = get_engine()
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    
    # Preset settings
    presets = {
        "instagram_reels": {"width": 1080, "height": 1920, "fps": 30, "bitrate": "8M"},
        "youtube_shorts": {"width": 1080, "height": 1920, "fps": 30, "bitrate": "10M"},
        "tiktok": {"width": 1080, "height": 1920, "fps": 30, "bitrate": "8M"},
        "youtube": {"width": 1920, "height": 1080, "fps": 30, "bitrate": "12M"},
    }
    
    settings = presets.get(preset, presets["instagram_reels"])
    
    with Session(engine) as session:
        # Get final video
        final_path = get_final_video_path(UUID(project_id), UUID(run_id))
        if not final_path.exists():
            # Fall back to stitched
            final_path = get_stitched_video_path(UUID(project_id), UUID(run_id))
        
        if not final_path.exists():
            raise ValueError("No video found to export")
        
        # Export directory
        export_dir = BASE_DIR / "data" / "exports" / run_id
        export_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = export_dir / f"{preset}.mp4"
        
        # Create export record
        export_record = FinalExport(
            run_id=UUID(run_id),
            preset=ExportPreset(preset) if preset in [e.value for e in ExportPreset] else ExportPreset.CUSTOM,
            status=ExportStatus.RUNNING,
            width=settings["width"],
            height=settings["height"],
            fps=settings["fps"],
        )
        session.add(export_record)
        session.commit()
        
        try:
            # FFmpeg export with preset settings
            cmd = [
                "ffmpeg", "-y",
                "-i", str(final_path),
                "-vf", f"scale={settings['width']}:{settings['height']}:force_original_aspect_ratio=decrease,pad={settings['width']}:{settings['height']}:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-b:v", settings["bitrate"],
                "-c:a", "aac",
                "-b:a", "192k",
                "-preset", "medium",
                str(output_path),
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
            
            if result.returncode != 0:
                # Fallback: just copy
                import shutil
                shutil.copy2(final_path, output_path)
            
            # Update export record
            export_record.status = ExportStatus.SUCCEEDED
            export_record.file_path = str(output_path)
            export_record.file_size_bytes = output_path.stat().st_size if output_path.exists() else 0
            export_record.finished_at = datetime.utcnow()
            session.add(export_record)
            session.commit()
            session.refresh(export_record)
            
            write_log(project_id, run_id, f"Export complete: {output_path}")
            
            return {
                "export_id": str(export_record.id),
                "file_path": str(output_path),
            }
            
        except Exception as e:
            export_record.status = ExportStatus.FAILED
            export_record.error_message = str(e)
            session.add(export_record)
            session.commit()
            raise
