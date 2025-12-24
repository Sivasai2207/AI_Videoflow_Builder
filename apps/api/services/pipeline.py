"""
Pipeline Service

Manages resumable DAG execution for the video generation pipeline.
"""
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID
from enum import Enum

from sqlmodel import Session

from models import Run


class NodeStatus(str, Enum):
    """Status of a pipeline node."""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineNode:
    """Represents a node in the pipeline DAG."""
    
    def __init__(
        self, 
        node_id: str, 
        node_type: str,
        inputs: Dict[str, Any],
        depends_on: list[str] = None,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.inputs = inputs
        self.depends_on = depends_on or []
        self.status = NodeStatus.NOT_STARTED
        self.output_path: Optional[str] = None
        self.error: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
    
    def compute_input_hash(self) -> str:
        """Compute hash of inputs for caching."""
        input_str = json.dumps(self.inputs, sort_keys=True)
        return hashlib.sha256(input_str.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """Serialize node to dict."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status.value,
            "input_hash": self.compute_input_hash(),
            "output_path": self.output_path,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


def get_node_status(run: Run, node_id: str) -> NodeStatus:
    """Get the status of a specific node in a run."""
    if not run.node_status_json:
        return NodeStatus.NOT_STARTED
    
    nodes = run.node_status_json.get("nodes", {})
    node_data = nodes.get(node_id)
    
    if not node_data:
        return NodeStatus.NOT_STARTED
    
    return NodeStatus(node_data.get("status", "not_started"))


def update_node_status(
    session: Session,
    run: Run,
    node_id: str,
    status: NodeStatus,
    output_path: Optional[str] = None,
    error: Optional[str] = None,
):
    """Update the status of a node in the run's pipeline state."""
    if not run.node_status_json:
        run.node_status_json = {"nodes": {}, "updated_at": None}
    
    nodes = run.node_status_json.get("nodes", {})
    
    nodes[node_id] = {
        "status": status.value,
        "output_path": output_path,
        "error": error,
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    run.node_status_json = {
        "nodes": nodes,
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    session.add(run)
    session.commit()


def is_node_completed(run: Run, node_id: str) -> bool:
    """Check if a node is already completed (for resumability)."""
    status = get_node_status(run, node_id)
    return status == NodeStatus.COMPLETED


def get_completed_nodes(run: Run) -> list[str]:
    """Get list of completed node IDs."""
    if not run.node_status_json:
        return []
    
    nodes = run.node_status_json.get("nodes", {})
    return [
        node_id for node_id, data in nodes.items()
        if data.get("status") == "completed"
    ]


def get_pending_nodes(run: Run, all_nodes: list[str]) -> list[str]:
    """Get list of nodes that still need to run."""
    completed = set(get_completed_nodes(run))
    return [n for n in all_nodes if n not in completed]


def reset_failed_nodes(session: Session, run: Run):
    """Reset failed nodes so they can be retried."""
    if not run.node_status_json:
        return
    
    nodes = run.node_status_json.get("nodes", {})
    
    for node_id, data in nodes.items():
        if data.get("status") == "failed":
            data["status"] = "not_started"
            data["error"] = None
    
    run.node_status_json = {
        "nodes": nodes,
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    session.add(run)
    session.commit()


def build_shot_nodes(run: Run) -> list[str]:
    """Build list of node IDs for all shots."""
    if not run.director_json:
        return []
    
    shots = run.director_json.get("shots", [])
    nodes = []
    
    # Hero frames
    nodes.append("hero_style")
    nodes.append("hero_character")
    
    # Per-shot nodes
    for shot in shots:
        shot_id = shot.get("shot_id")
        if shot_id:
            nodes.append(f"keyframe_{shot_id}")
            nodes.append(f"qc_{shot_id}")
            nodes.append(f"video_{shot_id}")
    
    # Final nodes
    nodes.append("stitch")
    nodes.append("voiceover")
    nodes.append("final_mux")
    nodes.append("export")
    
    return nodes


def get_cache_path(project_id: UUID, run_id: UUID, node_id: str, input_hash: str) -> Path:
    """Get cache path for a node's output."""
    from config import PROJECTS_DIR
    
    cache_dir = PROJECTS_DIR / str(project_id) / "runs" / str(run_id) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    return cache_dir / f"{node_id}_{input_hash}"


def check_cache(project_id: UUID, run_id: UUID, node_id: str, input_hash: str) -> Optional[str]:
    """Check if output exists in cache."""
    cache_path = get_cache_path(project_id, run_id, node_id, input_hash)
    
    # Check for marker file
    marker = cache_path.with_suffix(".done")
    if marker.exists():
        # Read output path from marker
        return marker.read_text().strip()
    
    return None


def write_cache(
    project_id: UUID, 
    run_id: UUID, 
    node_id: str, 
    input_hash: str, 
    output_path: str
):
    """Write output to cache."""
    cache_path = get_cache_path(project_id, run_id, node_id, input_hash)
    marker = cache_path.with_suffix(".done")
    marker.write_text(output_path)
