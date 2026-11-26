from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.api.dependencies import get_artifact_store, get_session
from src.control_plane.infrastructure.artifacts import ArtifactStore
from src.control_plane.infrastructure.database.models import Artifact

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: UUID,
    session: AsyncSession = Depends(get_session),
    store: ArtifactStore = Depends(get_artifact_store),
):
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not artifact.local_available:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Artifact is no longer retained locally; use the run's GitHub repository",
        )
    try:
        path = store.resolve(artifact.storage_key)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(
            status_code=404, detail="Artifact file not found"
        ) from error
    return FileResponse(path, filename=artifact.filename, media_type=artifact.mime_type)
