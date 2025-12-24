from pathlib import Path
from uuid import UUID

from config import PROJECTS_DIR


def get_project_path(project_id: UUID) -> Path:
    """Get the storage path for a project."""
    path = PROJECTS_DIR / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_run_path(project_id: UUID, run_id: UUID) -> Path:
    """Get the storage path for a run."""
    path = get_project_path(project_id) / "runs" / str(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_path(project_id: UUID, run_id: UUID) -> Path:
    """Get the logs path for a run."""
    run_path = get_run_path(project_id, run_id)
    return run_path / "logs.txt"


def write_log(project_id: UUID, run_id: UUID, message: str) -> None:
    """Append a message to the run's log file."""
    logs_path = get_logs_path(project_id, run_id)
    with open(logs_path, "a") as f:
        f.write(message + "\n")
