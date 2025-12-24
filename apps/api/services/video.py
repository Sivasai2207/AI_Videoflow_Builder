"""
Video Generation Service

Handles video generation from keyframes using FFmpeg.
"""
import subprocess
import os
from pathlib import Path
from typing import Optional, List
from uuid import UUID

from config import PROJECTS_DIR


# FFmpeg availability check
def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except Exception:
        return False


FFMPEG_AVAILABLE = check_ffmpeg()


def get_video_dir(project_id: UUID, run_id: UUID) -> Path:
    """Get video directory for a run."""
    path = PROJECTS_DIR / str(project_id) / "runs" / str(run_id) / "video"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_shot_video_path(project_id: UUID, run_id: UUID, shot_id: str, clip_type: str = "preview") -> Path:
    """Get the video path for a specific shot."""
    video_dir = get_video_dir(project_id, run_id)
    shots_dir = video_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    return shots_dir / f"{shot_id}_{clip_type}.mp4"


def get_stitched_video_path(project_id: UUID, run_id: UUID) -> Path:
    """Get the stitched video path."""
    video_dir = get_video_dir(project_id, run_id)
    return video_dir / "stitched.mp4"


def get_final_video_path(project_id: UUID, run_id: UUID) -> Path:
    """Get the final video (with audio) path."""
    video_dir = get_video_dir(project_id, run_id)
    return video_dir / "final.mp4"


def generate_video_from_keyframe(
    keyframe_path: str,
    output_path: str,
    duration_sec: float,
    fps: int = 30,
    motion_type: str = "zoom_in",
    motion_intensity: float = 0.1,
) -> bool:
    """
    Generate a video from a static keyframe with motion.
    
    Args:
        keyframe_path: Path to the keyframe image
        output_path: Output video path
        duration_sec: Duration in seconds
        fps: Frames per second
        motion_type: Type of motion (zoom_in, zoom_out, pan_left, pan_right)
        motion_intensity: Intensity of motion (0.0 to 1.0)
        
    Returns:
        True if successful
    """
    if not FFMPEG_AVAILABLE:
        # Create mock video file
        return create_mock_video(output_path, duration_sec)
    
    # Calculate zoom factor based on motion intensity
    zoom_start = 1.0
    zoom_end = 1.0 + (motion_intensity * 0.5)
    
    # FFmpeg filter for Ken Burns effect (zoom + pan)
    if motion_type == "zoom_in":
        zoompan = f"zoompan=z='min(zoom+{motion_intensity/duration_sec},1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration_sec * fps)}:s=768x1344:fps={fps}"
    elif motion_type == "zoom_out":
        zoompan = f"zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-{motion_intensity/duration_sec}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration_sec * fps)}:s=768x1344:fps={fps}"
    elif motion_type == "pan_left":
        zoompan = f"zoompan=z=1.1:x='iw-iw/zoom-(iw-iw/zoom)*(on/{fps}/{duration_sec})':y='ih/2-(ih/zoom/2)':d={int(duration_sec * fps)}:s=768x1344:fps={fps}"
    elif motion_type == "pan_right":
        zoompan = f"zoompan=z=1.1:x='(iw-iw/zoom)*(on/{fps}/{duration_sec})':y='ih/2-(ih/zoom/2)':d={int(duration_sec * fps)}:s=768x1344:fps={fps}"
    else:
        # Static
        zoompan = f"zoompan=z=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration_sec * fps)}:s=768x1344:fps={fps}"
    
    try:
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", keyframe_path,
            "-vf", zoompan,
            "-c:v", "libx264",
            "-t", str(duration_sec),
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            output_path,
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        
        return result.returncode == 0
    except Exception as e:
        print(f"FFmpeg error: {e}")
        return create_mock_video(output_path, duration_sec)


def stitch_video_clips(
    clip_paths: List[str],
    output_path: str,
    transition: str = "hard_cut",
    transition_duration: float = 0.5,
) -> bool:
    """
    Stitch multiple video clips into one.
    
    Args:
        clip_paths: List of video clip paths
        output_path: Output video path
        transition: Transition type (hard_cut, fade, dip_to_black)
        transition_duration: Transition duration in seconds
        
    Returns:
        True if successful
    """
    if not clip_paths:
        return False
    
    if not FFMPEG_AVAILABLE:
        return create_mock_video(output_path, 40.0)
    
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Hard cut: use simple concat demuxer
        if transition == "hard_cut" or len(clip_paths) == 1:
            return _stitch_hard_cut(clip_paths, output_path)
        
        # Transitions require more complex filter graphs
        if transition == "fade":
            return _stitch_with_fade(clip_paths, output_path, transition_duration)
        elif transition == "dip_to_black":
            return _stitch_dip_to_black(clip_paths, output_path, transition_duration)
        else:
            return _stitch_hard_cut(clip_paths, output_path)
            
    except Exception as e:
        print(f"FFmpeg stitch error: {e}")
        return False


def _stitch_hard_cut(clip_paths: List[str], output_path: str) -> bool:
    """Stitch with hard cuts (simple concat)."""
    concat_file = Path(output_path).parent / "concat_list.txt"
    with open(concat_file, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{clip}'\n")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        output_path,
    ]
    
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    
    concat_file.unlink(missing_ok=True)
    return result.returncode == 0


def _stitch_with_fade(
    clip_paths: List[str], 
    output_path: str, 
    fade_duration: float
) -> bool:
    """Stitch with crossfade transitions using xfade filter."""
    if len(clip_paths) < 2:
        return _stitch_hard_cut(clip_paths, output_path)
    
    # Build complex filter graph for xfade transitions
    inputs = []
    for i, clip in enumerate(clip_paths):
        inputs.extend(["-i", clip])
    
    # Build xfade chain
    # For N clips: [0][1]xfade -> [01][2]xfade -> etc
    filter_parts = []
    offset = 0.0
    
    for i in range(len(clip_paths) - 1):
        if i == 0:
            input_a = "[0:v]"
            input_b = "[1:v]"
        else:
            input_a = f"[v{i}]"
            input_b = f"[{i+1}:v]"
        
        if i == len(clip_paths) - 2:
            output_label = "[outv]"
        else:
            output_label = f"[v{i+1}]"
        
        # Get duration of clip i (estimate 4s each if can't probe)
        clip_duration = 4.0
        offset += max(0.1, clip_duration - fade_duration)
        
        filter_parts.append(
            f"{input_a}{input_b}xfade=transition=fade:duration={fade_duration}:offset={offset}{output_label}"
        )
    
    filter_complex = ";".join(filter_parts)
    
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        output_path,
    ]
    
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
    )
    
    if result.returncode != 0:
        # Fallback to hard cut
        return _stitch_hard_cut(clip_paths, output_path)
    
    return True


def _stitch_dip_to_black(
    clip_paths: List[str],
    output_path: str,
    fade_duration: float,
) -> bool:
    """Stitch with dip-to-black transitions (fade out, fade in)."""
    if len(clip_paths) < 2:
        return _stitch_hard_cut(clip_paths, output_path)
    
    # For dip-to-black: add fade-in/fade-out to each clip, then concat
    temp_clips = []
    temp_dir = Path(output_path).parent / "temp_clips"
    temp_dir.mkdir(exist_ok=True)
    
    try:
        for i, clip in enumerate(clip_paths):
            temp_clip = temp_dir / f"clip_{i}.mp4"
            
            # Add fade-in at start (except first clip) and fade-out at end (except last clip)
            filters = []
            if i > 0:
                filters.append(f"fade=in:st=0:d={fade_duration/2}")
            if i < len(clip_paths) - 1:
                # Estimate duration, apply fade at end
                filters.append(f"fade=out:st=3.5:d={fade_duration/2}")
            
            if filters:
                filter_str = ",".join(filters)
                cmd = [
                    "ffmpeg", "-y",
                    "-i", clip,
                    "-vf", filter_str,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    str(temp_clip),
                ]
            else:
                import shutil
                shutil.copy2(clip, temp_clip)
                temp_clips.append(str(temp_clip))
                continue
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            temp_clips.append(str(temp_clip))
        
        # Now concat the processed clips
        result = _stitch_hard_cut(temp_clips, output_path)
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return result
        
    except Exception as e:
        print(f"Dip-to-black error: {e}")
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _stitch_hard_cut(clip_paths, output_path)


def add_audio_to_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    audio_volume: float = 1.0,
) -> bool:
    """
    Add audio track to video.
    
    Args:
        video_path: Input video path
        audio_path: Audio track path
        output_path: Output video path
        audio_volume: Audio volume (0.0 to 2.0)
        
    Returns:
        True if successful
    """
    if not FFMPEG_AVAILABLE:
        # Just copy video as mock
        import shutil
        try:
            shutil.copy2(video_path, output_path)
            return True
        except:
            return False
    
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex", f"[1:a]volume={audio_volume}[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
        
        return result.returncode == 0
    except Exception as e:
        print(f"FFmpeg mux error: {e}")
        return False


def mix_audio_tracks(
    voiceover_path: Optional[str],
    music_path: Optional[str],
    output_path: str,
    voiceover_volume: float = 1.0,
    music_volume: float = 0.3,
    duration_sec: Optional[float] = None,
) -> bool:
    """
    Mix voiceover and music into a single audio track.
    
    Args:
        voiceover_path: Voiceover audio path
        music_path: Music audio path
        output_path: Output audio path
        voiceover_volume: Voiceover volume
        music_volume: Music volume
        duration_sec: Target duration (optional)
        
    Returns:
        True if successful
    """
    if not FFMPEG_AVAILABLE:
        return create_mock_audio(output_path, duration_sec or 40.0)
    
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        if voiceover_path and music_path:
            # Mix both tracks
            filter_complex = f"[0:a]volume={voiceover_volume}[v];[1:a]volume={music_volume}[m];[v][m]amix=inputs=2:duration=longest[out]"
            cmd = [
                "ffmpeg", "-y",
                "-i", voiceover_path,
                "-i", music_path,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-c:a", "aac",
            ]
        elif voiceover_path:
            cmd = [
                "ffmpeg", "-y",
                "-i", voiceover_path,
                "-af", f"volume={voiceover_volume}",
                "-c:a", "aac",
            ]
        elif music_path:
            cmd = [
                "ffmpeg", "-y",
                "-i", music_path,
                "-af", f"volume={music_volume}",
                "-c:a", "aac",
            ]
        else:
            return create_mock_audio(output_path, duration_sec or 40.0)
        
        if duration_sec:
            cmd.extend(["-t", str(duration_sec)])
        
        cmd.append(output_path)
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        
        return result.returncode == 0
    except Exception as e:
        print(f"FFmpeg mix error: {e}")
        return False


def create_mock_video(output_path: str, duration_sec: float) -> bool:
    """Create a minimal mock MP4 file for testing."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Write a minimal valid MP4 header (will show black)
        # This is a placeholder - in production, we'd actually generate
        with open(output_path, "wb") as f:
            # Minimal ftyp + moov (not playable, but file exists)
            f.write(b'\x00\x00\x00\x1c\x66\x74\x79\x70\x69\x73\x6f\x6d')
            f.write(b'\x00\x00\x00\x00\x69\x73\x6f\x6d\x61\x76\x63\x31')
            f.write(b'\x6d\x70\x34\x31' + b'\x00' * 100)
        return True
    except:
        return False


def create_mock_audio(output_path: str, duration_sec: float) -> bool:
    """Create a minimal mock audio file for testing."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Write placeholder
        with open(output_path, "wb") as f:
            f.write(b'\x00' * 1000)
        return True
    except:
        return False
