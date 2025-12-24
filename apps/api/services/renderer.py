"""
Renderer Adapter Service

Abstraction layer for rendering (ComfyUI local vs remote GPU worker).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import UUID

from models.system_model import RendererTarget


@dataclass
class RenderRequest:
    """Request to render an image or video."""
    workflow_id: str
    inputs: Dict[str, Any]
    output_dir: Path
    job_id: Optional[str] = None


@dataclass
class RenderResult:
    """Result from a render operation."""
    success: bool
    output_paths: List[str]
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class RendererAdapter(ABC):
    """Abstract base class for render adapters."""
    
    @abstractmethod
    def render_image(self, request: RenderRequest) -> RenderResult:
        """Render an image from a workflow."""
        pass
    
    @abstractmethod
    def render_video(self, request: RenderRequest) -> RenderResult:
        """Render a video from a workflow."""
        pass
    
    @abstractmethod
    def check_health(self) -> bool:
        """Check if the renderer is available."""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get detailed status of the renderer."""
        pass


class LocalComfyUIAdapter(RendererAdapter):
    """Adapter for local ComfyUI instance."""
    
    def __init__(self, comfyui_url: str = "http://127.0.0.1:8188"):
        self.comfyui_url = comfyui_url
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            from services.comfyui import ComfyUIClient
            self._client = ComfyUIClient(self.comfyui_url)
        return self._client
    
    def render_image(self, request: RenderRequest) -> RenderResult:
        """Render image via local ComfyUI."""
        import time
        start_time = time.time()
        
        try:
            from services.images import build_workflow
            
            # Build workflow from request
            workflow = build_workflow(
                request.workflow_id,
                request.inputs.get("prompt", ""),
                request.inputs.get("negative_prompt", ""),
                request.inputs.get("seed", 12345),
                request.inputs.get("filename_prefix", "render"),
                **request.inputs.get("params", {}),
            )
            
            # Submit and poll
            prompt_id = self.client.submit_workflow(workflow)
            history = self.client.poll_until_complete(prompt_id)
            output_files = self.client.collect_outputs(history, request.output_dir)
            
            duration = time.time() - start_time
            
            return RenderResult(
                success=len(output_files) > 0,
                output_paths=[str(f) for f in output_files],
                duration_seconds=duration,
            )
            
        except Exception as e:
            return RenderResult(
                success=False,
                output_paths=[],
                error=str(e),
                duration_seconds=time.time() - start_time,
            )
    
    def render_video(self, request: RenderRequest) -> RenderResult:
        """Render video via local FFmpeg (images to video)."""
        import time
        start_time = time.time()
        
        try:
            from services.video import create_video_from_image
            
            output_path = request.output_dir / f"{request.inputs.get('filename', 'video')}.mp4"
            
            success = create_video_from_image(
                request.inputs.get("image_path", ""),
                str(output_path),
                request.inputs.get("duration", 4.0),
                request.inputs.get("motion", "zoom_in"),
            )
            
            duration = time.time() - start_time
            
            return RenderResult(
                success=success,
                output_paths=[str(output_path)] if success else [],
                duration_seconds=duration,
            )
            
        except Exception as e:
            return RenderResult(
                success=False,
                output_paths=[],
                error=str(e),
                duration_seconds=time.time() - start_time,
            )
    
    def check_health(self) -> bool:
        """Check if ComfyUI is reachable."""
        return self.client.check_health_sync()
    
    def get_status(self) -> Dict[str, Any]:
        """Get ComfyUI status."""
        try:
            if self.check_health():
                return {
                    "status": "online",
                    "url": self.comfyui_url,
                    "type": "local_comfyui",
                }
            else:
                return {
                    "status": "offline",
                    "url": self.comfyui_url,
                    "type": "local_comfyui",
                }
        except Exception as e:
            return {
                "status": "error",
                "url": self.comfyui_url,
                "type": "local_comfyui",
                "error": str(e),
            }


class RemoteGPUWorkerAdapter(RendererAdapter):
    """Adapter for remote GPU worker (stub for future implementation)."""
    
    def __init__(self, worker_url: str):
        self.worker_url = worker_url
    
    def render_image(self, request: RenderRequest) -> RenderResult:
        """Render image via remote worker."""
        # TODO: Implement remote worker communication
        return RenderResult(
            success=False,
            output_paths=[],
            error="Remote GPU worker not yet implemented",
        )
    
    def render_video(self, request: RenderRequest) -> RenderResult:
        """Render video via remote worker."""
        # TODO: Implement remote worker communication
        return RenderResult(
            success=False,
            output_paths=[],
            error="Remote GPU worker not yet implemented",
        )
    
    def check_health(self) -> bool:
        """Check if remote worker is reachable."""
        # TODO: Implement health check
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get remote worker status."""
        return {
            "status": "not_implemented",
            "url": self.worker_url,
            "type": "remote_gpu_worker",
        }


def get_renderer(target: RendererTarget = RendererTarget.LOCAL_COMFYUI, **kwargs) -> RendererAdapter:
    """Factory function to get the appropriate renderer adapter."""
    if target == RendererTarget.LOCAL_COMFYUI:
        return LocalComfyUIAdapter(
            comfyui_url=kwargs.get("comfyui_url", "http://127.0.0.1:8188")
        )
    elif target == RendererTarget.REMOTE_GPU_WORKER:
        return RemoteGPUWorkerAdapter(
            worker_url=kwargs.get("worker_url", "http://localhost:5000")
        )
    else:
        raise ValueError(f"Unknown renderer target: {target}")
