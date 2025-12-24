"""
Audio Service

Handles voiceover generation and audio processing.
"""
import subprocess
from pathlib import Path
from typing import Optional
from uuid import UUID

from config import PROJECTS_DIR


def get_audio_dir(project_id: UUID, run_id: UUID) -> Path:
    """Get audio directory for a run."""
    path = PROJECTS_DIR / str(project_id) / "runs" / str(run_id) / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_voiceover(
    text: str,
    output_path: str,
    voice_id: str = "default",
    speed: float = 1.0,
) -> bool:
    """
    Generate voiceover audio from text.
    
    Uses gTTS if available, otherwise creates a mock file.
    
    Args:
        text: Script text
        output_path: Output audio path
        voice_id: Voice identifier
        speed: Speech speed multiplier
        
    Returns:
        True if successful
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Try gTTS first
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang='en', slow=speed < 0.9)
            tts.save(output_path)
            return True
        except ImportError:
            pass
        
        # Fallback: Create a silent audio file with duration based on text length
        # Roughly 150 words per minute = 2.5 words per second
        word_count = len(text.split())
        duration_sec = max(5.0, word_count / 2.5)
        
        return create_silent_audio(output_path, duration_sec)
        
    except Exception as e:
        print(f"Voiceover generation error: {e}")
        return False


def create_silent_audio(output_path: str, duration_sec: float) -> bool:
    """Create a silent audio file."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Try FFmpeg first
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=44100:cl=stereo:d={duration_sec}",
                "-c:a", "aac",
                output_path,
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if result.returncode == 0:
                return True
        except:
            pass
        
        # Fallback: Create minimal audio file
        with open(output_path, "wb") as f:
            f.write(b'\x00' * int(duration_sec * 1000))
        return True
        
    except Exception as e:
        print(f"Silent audio error: {e}")
        return False


def build_voiceover_script(director_json: dict) -> str:
    """
    Build a voiceover script from Director JSON.
    
    Uses logline and action beats to create a narrative.
    """
    creative = director_json.get("creative", {})
    logline = creative.get("logline", "")
    
    shots = director_json.get("shots", [])
    action_descriptions = []
    
    for shot in shots:
        beats = shot.get("action_beats", [])
        if beats:
            action_descriptions.append(". ".join(beats))
    
    # Combine into a script
    script_parts = []
    
    if logline:
        script_parts.append(logline)
    
    if action_descriptions:
        # Take a subset to keep voice manageable
        script_parts.extend(action_descriptions[:5])
    
    return ". ".join(script_parts) if script_parts else "A visual journey awaits."


def get_music_library() -> list[dict]:
    """
    Get available music tracks.
    
    In production, this would list actual music files.
    For now, returns placeholder options.
    """
    return [
        {
            "id": "ambient_1",
            "name": "Ambient Dreams",
            "duration_sec": 120,
            "genre": "ambient",
            "mood": "calm",
        },
        {
            "id": "cinematic_1",
            "name": "Epic Rising",
            "duration_sec": 90,
            "genre": "cinematic",
            "mood": "dramatic",
        },
        {
            "id": "upbeat_1",
            "name": "Energy Flow",
            "duration_sec": 60,
            "genre": "electronic",
            "mood": "energetic",
        },
    ]


def get_music_path(music_id: str) -> Optional[str]:
    """Get path to a music track by ID."""
    # In production, this would return actual file paths
    # For now, return None (music would need to be uploaded)
    return None
