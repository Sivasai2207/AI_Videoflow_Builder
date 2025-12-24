from uuid import UUID
from redis import Redis
from rq import Queue

from config import REDIS_URL

redis_conn = Redis.from_url(REDIS_URL)
task_queue = Queue("default", connection=redis_conn)


def enqueue_pipeline_job(run_id: UUID, project_id: UUID) -> str:
    """Enqueue a pipeline simulation job."""
    job = task_queue.enqueue(
        "tasks.simulate_pipeline.run_pipeline",
        str(run_id),
        str(project_id),
        job_timeout=600,
    )
    return job.id


def enqueue_director_job(
    run_id: UUID,
    project_id: UUID,
    user_id: UUID,
    request_data: dict,
) -> str:
    """Enqueue a Director plan generation job."""
    job = task_queue.enqueue(
        "tasks.director_generate.generate_director_plan",
        str(run_id),
        str(project_id),
        str(user_id),
        request_data,
        job_timeout=300,
    )
    return job.id


def enqueue_hero_frames_job(
    run_id: UUID,
    project_id: UUID,
    params: dict = None,
) -> str:
    """Enqueue a hero frames generation job."""
    job = task_queue.enqueue(
        "tasks.image_generation.generate_hero_frames",
        str(run_id),
        str(project_id),
        params,
        job_timeout=600,
    )
    return job.id


def enqueue_keyframe_job(
    run_id: UUID,
    project_id: UUID,
    shot_id: str,
    params: dict = None,
    seed_override: int = None,
) -> str:
    """Enqueue a single keyframe generation job."""
    job = task_queue.enqueue(
        "tasks.image_generation.generate_keyframe",
        str(run_id),
        str(project_id),
        shot_id,
        params,
        seed_override,
        job_timeout=300,
    )
    return job.id


def enqueue_keyframes_all_job(
    run_id: UUID,
    project_id: UUID,
    params: dict = None,
) -> str:
    """Enqueue a job to generate all keyframes."""
    job = task_queue.enqueue(
        "tasks.image_generation.generate_keyframes_all",
        str(run_id),
        str(project_id),
        params,
        job_timeout=1800,
    )
    return job.id


def enqueue_regenerate_keyframe_job(
    run_id: UUID,
    project_id: UUID,
    shot_id: str,
    seed_mode: str = "new",
    params: dict = None,
) -> str:
    """Enqueue a keyframe regeneration job."""
    job = task_queue.enqueue(
        "tasks.image_generation.regenerate_keyframe",
        str(run_id),
        str(project_id),
        shot_id,
        seed_mode,
        params,
        job_timeout=300,
    )
    return job.id


# Phase 4: Video generation jobs

def enqueue_shot_video_job(
    run_id: UUID,
    project_id: UUID,
    shot_id: str,
    clip_type: str = "preview",
) -> str:
    """Enqueue a single shot video generation job."""
    job = task_queue.enqueue(
        "tasks.video_generation.generate_shot_video",
        str(run_id),
        str(project_id),
        shot_id,
        clip_type,
        job_timeout=300,
    )
    return job.id


def enqueue_all_videos_job(
    run_id: UUID,
    project_id: UUID,
    clip_type: str = "preview",
) -> str:
    """Enqueue a job to generate all shot videos."""
    job = task_queue.enqueue(
        "tasks.video_generation.generate_all_videos",
        str(run_id),
        str(project_id),
        clip_type,
        job_timeout=1800,
    )
    return job.id


def enqueue_stitch_job(
    run_id: UUID,
    project_id: UUID,
) -> str:
    """Enqueue a video stitch job."""
    job = task_queue.enqueue(
        "tasks.video_generation.stitch_final_video",
        str(run_id),
        str(project_id),
        job_timeout=600,
    )
    return job.id


def enqueue_voiceover_job(
    run_id: UUID,
    project_id: UUID,
    script: str = None,
) -> str:
    """Enqueue a voiceover generation job."""
    job = task_queue.enqueue(
        "tasks.video_generation.generate_voiceover_track",
        str(run_id),
        str(project_id),
        script,
        job_timeout=300,
    )
    return job.id


def enqueue_final_video_job(
    run_id: UUID,
    project_id: UUID,
    include_voiceover: bool = True,
    include_music: bool = False,
) -> str:
    """Enqueue a final video (with audio) job."""
    job = task_queue.enqueue(
        "tasks.video_generation.create_final_with_audio",
        str(run_id),
        str(project_id),
        include_voiceover,
        include_music,
        job_timeout=600,
    )
    return job.id


def enqueue_export_job(
    run_id: UUID,
    project_id: UUID,
    preset: str = "instagram_reels",
) -> str:
    """Enqueue a video export job."""
    job = task_queue.enqueue(
        "tasks.video_generation.export_video",
        str(run_id),
        str(project_id),
        preset,
        job_timeout=600,
    )
    return job.id


# Phase 5: Quality + Variants jobs

def enqueue_variants_job(
    run_id: UUID,
    project_id: UUID,
    shot_id: str,
    count: int = 3,
    seed_mode: str = "offset",
    reference_strategy: str = "hero_plus_prev",
) -> str:
    """Enqueue a keyframe variants generation job."""
    job = task_queue.enqueue(
        "tasks.image_generation.generate_variants",
        str(run_id),
        str(project_id),
        shot_id,
        count,
        seed_mode,
        reference_strategy,
        job_timeout=900,  # 15 min for multiple variants
    )
    return job.id


def enqueue_qc_keyframes_job(
    run_id: UUID,
    project_id: UUID,
) -> str:
    """Enqueue a QC job for keyframes."""
    job = task_queue.enqueue(
        "tasks.qc.run_keyframe_qc_all",
        str(run_id),
        str(project_id),
        job_timeout=300,
    )
    return job.id


def enqueue_stitch_with_transitions_job(
    run_id: UUID,
    project_id: UUID,
    transition: str = "hard_cut",
    transition_duration: float = 0.5,
) -> str:
    """Enqueue a video stitch job with transitions."""
    job = task_queue.enqueue(
        "tasks.video_generation.stitch_with_transitions",
        str(run_id),
        str(project_id),
        transition,
        transition_duration,
        job_timeout=600,
    )
    return job.id

