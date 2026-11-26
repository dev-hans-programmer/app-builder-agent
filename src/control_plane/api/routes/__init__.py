from fastapi import APIRouter, Depends

from src.control_plane.api.dependencies import require_api_key
from src.control_plane.api.routes.artifacts import router as artifacts_router
from src.control_plane.api.routes.projects import router as projects_router
from src.control_plane.api.routes.runs import router as runs_router

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(projects_router)
api_router.include_router(runs_router)
api_router.include_router(artifacts_router)
