"""
ComfyUI Client Service

HTTP client for communicating with local ComfyUI server.
"""
import json
import time
import shutil
from pathlib import Path
from typing import Optional
import httpx
import os

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
COMFYUI_OUTPUT_DIR = os.getenv("COMFYUI_OUTPUT_DIR", "/data/comfyui/outputs")


class ComfyUIClient:
    """Client for interacting with ComfyUI API."""
    
    def __init__(self, base_url: str = COMFYUI_URL):
        self.base_url = base_url
        self.timeout = 120.0
    
    async def check_health(self) -> bool:
        """Check if ComfyUI is running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except Exception:
            return False
    
    def check_health_sync(self) -> bool:
        """Check if ComfyUI is running (sync version for workers)."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except Exception:
            return False
    
    def submit_workflow(self, workflow: dict, client_id: str = "video-gen-ai") -> str:
        """
        Submit a workflow to ComfyUI.
        
        Args:
            workflow: The ComfyUI workflow JSON
            client_id: Client identifier for tracking
            
        Returns:
            prompt_id: The ID to track this job
        """
        payload = {
            "prompt": workflow,
            "client_id": client_id,
        }
        
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/prompt",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("prompt_id", "")
    
    def get_queue_status(self) -> dict:
        """Get current queue status."""
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{self.base_url}/queue")
            response.raise_for_status()
            return response.json()
    
    def get_history(self, prompt_id: str) -> Optional[dict]:
        """Get execution history for a prompt."""
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{self.base_url}/history/{prompt_id}")
            if response.status_code == 200:
                data = response.json()
                return data.get(prompt_id)
            return None
    
    def poll_until_complete(
        self,
        prompt_id: str,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
        on_progress: Optional[callable] = None,
    ) -> dict:
        """
        Poll until a prompt completes.
        
        Args:
            prompt_id: The prompt ID to track
            timeout: Maximum wait time in seconds
            poll_interval: Time between polls
            on_progress: Optional callback for progress updates
            
        Returns:
            History entry with outputs
            
        Raises:
            TimeoutError: If prompt doesn't complete in time
            RuntimeError: If prompt fails
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check history for completion
            history = self.get_history(prompt_id)
            
            if history:
                outputs = history.get("outputs", {})
                status = history.get("status", {})
                
                if status.get("completed", False):
                    return history
                
                if "error" in status or status.get("status_str") == "error":
                    error_msg = status.get("messages", [{"text": "Unknown error"}])
                    raise RuntimeError(f"ComfyUI execution failed: {error_msg}")
            
            # Check queue status for position
            queue = self.get_queue_status()
            running = queue.get("queue_running", [])
            pending = queue.get("queue_pending", [])
            
            # Find position in queue
            position = None
            for i, item in enumerate(pending):
                if len(item) > 1 and item[1] == prompt_id:
                    position = i + 1
                    break
            
            if on_progress:
                on_progress({
                    "status": "running" if any(p[1] == prompt_id for p in running if len(p) > 1) else "queued",
                    "position": position,
                })
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")
    
    def collect_outputs(self, history: dict, output_dir: Path) -> list[Path]:
        """
        Collect output files from ComfyUI history.
        
        Args:
            history: The history entry from ComfyUI
            output_dir: Directory to copy outputs to
            
        Returns:
            List of output file paths
        """
        output_files = []
        outputs = history.get("outputs", {})
        
        for node_id, node_outputs in outputs.items():
            images = node_outputs.get("images", [])
            
            for img in images:
                filename = img.get("filename", "")
                subfolder = img.get("subfolder", "")
                
                if filename:
                    # Build source path
                    if subfolder:
                        src_path = Path(COMFYUI_OUTPUT_DIR) / subfolder / filename
                    else:
                        src_path = Path(COMFYUI_OUTPUT_DIR) / filename
                    
                    if src_path.exists():
                        # Copy to our output directory
                        output_dir.mkdir(parents=True, exist_ok=True)
                        dst_path = output_dir / filename
                        shutil.copy2(src_path, dst_path)
                        output_files.append(dst_path)
        
        return output_files


def build_workflow_from_template(
    template_path: Path,
    replacements: dict,
) -> dict:
    """
    Build a workflow from a template with replacements.
    
    Args:
        template_path: Path to workflow template JSON
        replacements: Dict of placeholder -> value to replace
        
    Returns:
        Workflow dict ready for ComfyUI
    """
    with open(template_path) as f:
        template_str = f.read()
    
    # Replace placeholders
    for key, value in replacements.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, str):
            template_str = template_str.replace(placeholder, value)
        else:
            template_str = template_str.replace(f'"{placeholder}"', str(value))
            template_str = template_str.replace(placeholder, str(value))
    
    return json.loads(template_str)


# Create singleton client
comfyui_client = ComfyUIClient()
