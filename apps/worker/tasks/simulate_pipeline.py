"""
Simulate Pipeline Task

This is a fake pipeline job that simulates video generation progress.
It updates the database and writes logs to demonstrate the full pipeline infrastructure.
"""
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, create_engine, select

# Import models from API
import sys
API_DIR = Path(__file__).resolve().parent.parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from models.run import Run, RunStatus
from models.render_job import RenderJob, JobStatus


def get_engine():
    """Create database engine."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    DB_PATH = BASE_DIR / "data" / "db" / "app.sqlite"
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def get_logs_path(project_id: str, run_id: str) -> Path:
    """Get logs path for a run."""
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    logs_path = BASE_DIR / "data" / "projects" / project_id / "runs" / run_id / "logs.txt"
    logs_path.parent.mkdir(parents=True, exist_ok=True)
    return logs_path


def write_log(project_id: str, run_id: str, message: str):
    """Write a log message."""
    logs_path = get_logs_path(project_id, run_id)
    timestamp = datetime.utcnow().isoformat()
    with open(logs_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def run_pipeline(run_id: str, project_id: str):
    """
    Simulate a video generation pipeline.
    
    This job:
    1. Updates run status from queued → running
    2. Simulates progress from 0% → 100%
    3. Writes log messages to disk
    4. Marks run as succeeded
    
    In future phases, this will be replaced with actual ComfyUI calls.
    """
    engine = get_engine()
    
    with Session(engine) as session:
        # Get the run and job
        run = session.get(Run, UUID(run_id))
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        statement = select(RenderJob).where(RenderJob.run_id == UUID(run_id))
        job = session.exec(statement).first()
        
        # Update to running
        run.status = RunStatus.RUNNING
        run.progress = 0
        if job:
            job.status = JobStatus.RUNNING
            job.logs_path = str(get_logs_path(project_id, run_id))
            session.add(job)
        session.add(run)
        session.commit()
        
        write_log(project_id, run_id, "Pipeline started")
        write_log(project_id, run_id, f"Project ID: {project_id}")
        write_log(project_id, run_id, f"Run ID: {run_id}")
        
        # Simulate pipeline stages
        stages = [
            ("Initializing pipeline", 10),
            ("Loading models", 20),
            ("Generating storyboard", 35),
            ("Creating hero frames", 50),
            ("Generating keyframes", 65),
            ("Creating preview clips", 80),
            ("Stitching final video", 95),
            ("Finalizing export", 100),
        ]
        
        for stage_name, target_progress in stages:
            write_log(project_id, run_id, f"Stage: {stage_name}")
            
            # Simulate work with gradual progress
            current = run.progress
            while current < target_progress:
                current = min(current + 5, target_progress)
                time.sleep(0.3)  # Simulate work
                
                # Update progress in database
                session.refresh(run)
                run.progress = current
                session.add(run)
                session.commit()
            
            write_log(project_id, run_id, f"Completed: {stage_name} ({target_progress}%)")
        
        # Mark as succeeded
        run.status = RunStatus.SUCCEEDED
        run.progress = 100
        run.finished_at = datetime.utcnow()
        if job:
            job.status = JobStatus.SUCCEEDED
            job.progress = 100
            session.add(job)
        session.add(run)
        session.commit()
        
        write_log(project_id, run_id, "Pipeline completed successfully")
        
        return {"status": "success", "run_id": run_id}
