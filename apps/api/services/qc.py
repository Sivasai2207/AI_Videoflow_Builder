"""
Quality Control (QC) Service

Performs quality checks on keyframes and video clips.
"""
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class QCResult:
    """Result of a quality check."""
    passed: bool
    warnings: list[str]
    errors: list[str]
    scores: dict[str, float]
    auto_regen_suggested: bool


def check_blur_score(image_path: str) -> float:
    """
    Calculate blur score using Laplacian variance.
    
    Higher score = sharper image.
    Typical thresholds:
    - < 100: Very blurry
    - 100-500: Slightly blurry
    - > 500: Sharp
    
    Returns:
        Blur score (higher is sharper)
    """
    try:
        # Try using OpenCV if available
        import cv2
        import numpy as np
        
        image = cv2.imread(image_path)
        if image is None:
            return 0.0
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        return float(laplacian_var)
    except ImportError:
        # Fallback: Use ImageMagick if available
        try:
            result = subprocess.run(
                ["identify", "-verbose", image_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Simple heuristic based on file complexity
            return 500.0  # Assume sharp if we can't check
        except:
            return 500.0  # Default to passing


def check_aspect_ratio(image_path: str, target_ratio: str) -> tuple[bool, str]:
    """
    Check if image matches target aspect ratio.
    
    Args:
        image_path: Path to image
        target_ratio: Target ratio like "9:16" or "16:9"
        
    Returns:
        (matches, actual_ratio)
    """
    try:
        # Try PIL first
        from PIL import Image
        
        with Image.open(image_path) as img:
            width, height = img.size
    except ImportError:
        # Fallback to ImageMagick
        try:
            result = subprocess.run(
                ["identify", "-format", "%w %h", image_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            parts = result.stdout.strip().split()
            width, height = int(parts[0]), int(parts[1])
        except:
            return True, "unknown"
    
    actual_ratio = width / height
    
    # Parse target ratio
    target_parts = target_ratio.split(":")
    target_w, target_h = float(target_parts[0]), float(target_parts[1])
    target = target_w / target_h
    
    # Allow 5% tolerance
    tolerance = 0.05
    matches = abs(actual_ratio - target) / target < tolerance
    
    actual_str = f"{width}:{height}"
    return matches, actual_str


def check_dimensions(image_path: str, min_width: int = 512, min_height: int = 512) -> tuple[bool, tuple[int, int]]:
    """
    Check if image meets minimum dimension requirements.
    
    Returns:
        (meets_requirements, (width, height))
    """
    try:
        from PIL import Image
        
        with Image.open(image_path) as img:
            width, height = img.size
            meets = width >= min_width and height >= min_height
            return meets, (width, height)
    except:
        return True, (0, 0)


def check_face_present(image_path: str) -> tuple[bool, int]:
    """
    Check if a face is present in the image.
    
    Returns:
        (face_found, face_count)
    """
    try:
        import cv2
        
        # Load OpenCV's pre-trained face detector
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        image = cv2.imread(image_path)
        if image is None:
            return False, 0
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        return len(faces) > 0, len(faces)
    except:
        # If OpenCV not available, assume no face check
        return True, 0


def check_clip_duration(
    clip_path: str, 
    target_duration: float, 
    tolerance: float = 0.5
) -> tuple[bool, float]:
    """
    Check if video clip duration matches target.
    
    Returns:
        (within_tolerance, actual_duration)
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                clip_path
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        actual = float(result.stdout.strip())
        within = abs(actual - target_duration) <= tolerance
        
        return within, actual
    except:
        return True, target_duration


def check_clip_fps(clip_path: str, target_fps: int = 30) -> tuple[bool, float]:
    """
    Check if video clip FPS matches target.
    
    Returns:
        (matches, actual_fps)
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                clip_path
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Parse fraction like "30/1"
        parts = result.stdout.strip().split("/")
        if len(parts) == 2:
            actual = float(parts[0]) / float(parts[1])
        else:
            actual = float(parts[0])
        
        matches = abs(actual - target_fps) < 1
        return matches, actual
    except:
        return True, float(target_fps)


def run_keyframe_qc(
    image_path: str,
    target_ratio: str = "9:16",
    blur_threshold: float = 100.0,
    check_face: bool = False,
) -> QCResult:
    """
    Run full QC on a keyframe image.
    
    Args:
        image_path: Path to keyframe
        target_ratio: Expected aspect ratio
        blur_threshold: Minimum blur score
        check_face: Whether to require face
        
    Returns:
        QCResult with status, warnings, scores
    """
    warnings = []
    errors = []
    scores = {}
    
    # Check if file exists
    if not Path(image_path).exists():
        return QCResult(
            passed=False,
            warnings=[],
            errors=["File not found"],
            scores={},
            auto_regen_suggested=True,
        )
    
    # Blur check
    blur_score = check_blur_score(image_path)
    scores["blur"] = blur_score
    
    if blur_score < blur_threshold:
        warnings.append(f"Image may be blurry (score: {blur_score:.1f}, threshold: {blur_threshold})")
    
    # Aspect ratio check
    ratio_ok, actual_ratio = check_aspect_ratio(image_path, target_ratio)
    scores["aspect_match"] = 1.0 if ratio_ok else 0.0
    
    if not ratio_ok:
        errors.append(f"Aspect ratio mismatch: got {actual_ratio}, expected {target_ratio}")
    
    # Dimensions check
    dims_ok, (width, height) = check_dimensions(image_path)
    scores["dimensions_ok"] = 1.0 if dims_ok else 0.0
    
    if not dims_ok:
        warnings.append(f"Image resolution low: {width}x{height}")
    
    # Face check (optional)
    if check_face:
        face_found, face_count = check_face_present(image_path)
        scores["face_present"] = 1.0 if face_found else 0.0
        
        if not face_found:
            warnings.append("No face detected (required)")
    
    # Determine pass/fail
    passed = len(errors) == 0
    auto_regen = len(errors) > 0 or (blur_score < blur_threshold * 0.5)
    
    return QCResult(
        passed=passed,
        warnings=warnings,
        errors=errors,
        scores=scores,
        auto_regen_suggested=auto_regen,
    )


def run_clip_qc(
    clip_path: str,
    target_duration: float,
    target_fps: int = 30,
) -> QCResult:
    """
    Run full QC on a video clip.
    
    Args:
        clip_path: Path to video clip
        target_duration: Expected duration in seconds
        target_fps: Expected FPS
        
    Returns:
        QCResult with status, warnings, scores
    """
    warnings = []
    errors = []
    scores = {}
    
    # Check if file exists
    if not Path(clip_path).exists():
        return QCResult(
            passed=False,
            warnings=[],
            errors=["File not found"],
            scores={},
            auto_regen_suggested=True,
        )
    
    # Duration check
    duration_ok, actual_duration = check_clip_duration(clip_path, target_duration)
    scores["duration_match"] = 1.0 if duration_ok else 0.0
    
    if not duration_ok:
        warnings.append(f"Duration mismatch: {actual_duration:.1f}s vs target {target_duration}s")
    
    # FPS check
    fps_ok, actual_fps = check_clip_fps(clip_path, target_fps)
    scores["fps_match"] = 1.0 if fps_ok else 0.0
    
    if not fps_ok:
        warnings.append(f"FPS mismatch: {actual_fps:.1f} vs target {target_fps}")
    
    # File size check (sanity)
    file_size = Path(clip_path).stat().st_size
    if file_size < 1000:
        errors.append("Video file too small (likely corrupt)")
    
    passed = len(errors) == 0
    
    return QCResult(
        passed=passed,
        warnings=warnings,
        errors=errors,
        scores=scores,
        auto_regen_suggested=not passed,
    )
