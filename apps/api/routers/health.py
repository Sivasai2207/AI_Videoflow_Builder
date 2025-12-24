"""
Health Router

API endpoints for system health checks.
"""
import subprocess
from fastapi import APIRouter
import httpx

from config import REDIS_URL

router = APIRouter(tags=["health"])


async def check_comfyui_health() -> dict:
    """Check if ComfyUI is available."""
    import os
    comfyui_url = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{comfyui_url}/system_stats")
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "online",
                    "url": comfyui_url,
                    "vram_free": data.get("system", {}).get("vram_free"),
                }
            else:
                return {"status": "error", "url": comfyui_url, "code": response.status_code}
    except Exception as e:
        return {"status": "offline", "url": comfyui_url, "error": str(e)}


async def check_ollama_health() -> dict:
    """Check if Ollama is available."""
    import os
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{ollama_url}/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name") for m in data.get("models", [])]
                return {
                    "status": "online",
                    "url": ollama_url,
                    "models": models[:5],  # First 5 models
                }
            else:
                return {"status": "error", "url": ollama_url, "code": response.status_code}
    except Exception as e:
        return {"status": "offline", "url": ollama_url, "error": str(e)}


def check_ffmpeg_health() -> dict:
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode == 0:
            # Extract version from first line
            first_line = result.stdout.split("\n")[0]
            return {
                "status": "online",
                "version": first_line,
            }
        else:
            return {"status": "error", "code": result.returncode}
    except FileNotFoundError:
        return {"status": "not_installed", "error": "FFmpeg not found in PATH"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_redis_health() -> dict:
    """Check if Redis is available."""
    try:
        from redis import Redis
        
        redis_conn = Redis.from_url(REDIS_URL)
        redis_conn.ping()
        
        info = redis_conn.info()
        return {
            "status": "online",
            "url": REDIS_URL,
            "version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
        }
    except Exception as e:
        return {"status": "offline", "url": REDIS_URL, "error": str(e)}


@router.get("/health/comfyui")
async def comfyui_health():
    """Check ComfyUI status."""
    return await check_comfyui_health()


@router.get("/health/ollama")
async def ollama_health():
    """Check Ollama status."""
    return await check_ollama_health()


@router.get("/health/ffmpeg")
async def ffmpeg_health():
    """Check FFmpeg status."""
    return check_ffmpeg_health()


@router.get("/health/redis")
async def redis_health():
    """Check Redis status."""
    return check_redis_health()


@router.get("/health/all")
async def all_health():
    """Check all system components."""
    comfyui = await check_comfyui_health()
    ollama = await check_ollama_health()
    ffmpeg = check_ffmpeg_health()
    redis = check_redis_health()
    
    # Determine overall status
    all_online = all([
        comfyui.get("status") == "online",
        ollama.get("status") == "online",
        ffmpeg.get("status") == "online",
        redis.get("status") == "online",
    ])
    
    # Core services (required)
    core_online = all([
        redis.get("status") == "online",
    ])
    
    # Optional services
    optional_status = {
        "comfyui": comfyui.get("status"),
        "ollama": ollama.get("status"),
        "ffmpeg": ffmpeg.get("status"),
    }
    
    return {
        "overall": "healthy" if all_online else ("degraded" if core_online else "unhealthy"),
        "core_services": core_online,
        "components": {
            "comfyui": comfyui,
            "ollama": ollama,
            "ffmpeg": ffmpeg,
            "redis": redis,
        },
    }
