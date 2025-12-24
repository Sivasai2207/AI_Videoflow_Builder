from .auth import router as auth_router
from .projects import router as projects_router
from .runs import router as runs_router
from .shots import router as shots_router
from .assets import router as assets_router
from .plans import router as plans_router
from .images import router as images_router
from .video import router as video_router
from .audio import router as audio_router
from .export import router as export_router
from .qc import router as qc_router
from .health import router as health_router
from .system import router as system_router
from .models import router as models_router
from .performance import router as performance_router

__all__ = [
    "auth_router",
    "projects_router",
    "runs_router",
    "shots_router",
    "assets_router",
    "plans_router",
    "images_router",
    "video_router",
    "audio_router",
    "export_router",
    "qc_router",
    "health_router",
    # Phase 6
    "system_router",
    "models_router",
    "performance_router",
]
