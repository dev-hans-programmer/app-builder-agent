from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.api.contracts import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    RunCreate,
    RunResponse,
)
from src.control_plane.api.dependencies import get_session
from src.control_plane.application.commands import (
    CreateProjectCommand,
    CreateRunCommand,
)
from src.control_plane.application.projects import ProjectService
from src.control_plane.application.runs import RunService
from src.control_plane.infrastructure.database.repositories import (
    ProjectRepository,
    RunRepository,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: AsyncSession = Depends(get_session)
):
    return await ProjectService(session).create(
        CreateProjectCommand(**payload.model_dump())
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    projects, _ = await ProjectRepository(session).list(offset=offset, limit=limit)
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, session: AsyncSession = Depends(get_session)):
    return await ProjectService(session).require(project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
):
    return await ProjectService(session).update(
        project_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: UUID, session: AsyncSession = Depends(get_session)
):
    await ProjectService(session).archive(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    project_id: UUID,
    payload: RunCreate,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    project = await ProjectService(session).require(project_id)
    command_payload = payload.model_dump()
    command_payload["execution_mode"] = (
        payload.execution_mode or request.app.state.settings.execution_mode
    )
    run, created = await RunService(session).create(
        project, CreateRunCommand(**command_payload)
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = f"/api/v1/runs/{run.id}"
    return run


@router.get("/{project_id}/runs", response_model=list[RunResponse])
async def list_project_runs(
    project_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    await ProjectService(session).require(project_id)
    runs, _ = await RunRepository(session).list_for_project(
        project_id, offset=offset, limit=limit
    )
    return runs
