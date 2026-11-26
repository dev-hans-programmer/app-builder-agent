from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.api.contracts import (
    ActionResponse,
    ArtifactResponse,
    RunEventResponse,
    RunResponse,
    RunStepResponse,
)
from src.control_plane.api.dependencies import get_session
from src.control_plane.application.commands import CreateRunCommand
from src.control_plane.application.projects import ProjectService
from src.control_plane.application.runs import RunService
from src.control_plane.domain.run_status import TERMINAL_RUN_STATUSES
from src.control_plane.infrastructure.database.repositories import RunRepository

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: UUID, session: AsyncSession = Depends(get_session)):
    return await RunService(session).require(run_id)


@router.get("/{run_id}/steps", response_model=list[RunStepResponse])
async def get_run_steps(run_id: UUID, session: AsyncSession = Depends(get_session)):
    await RunService(session).require(run_id)
    return await RunRepository(session).steps(run_id)


@router.get("/{run_id}/events", response_model=list[RunEventResponse])
async def get_run_events(
    run_id: UUID,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    await RunService(session).require(run_id)
    return await RunRepository(session).events(run_id, after_id=after_id, limit=limit)


@router.get("/{run_id}/logs", response_model=list[RunEventResponse])
async def get_run_logs(
    run_id: UUID,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    await RunService(session).require(run_id)
    return await RunRepository(session).events(
        run_id, after_id=after_id, limit=limit, logs_only=True
    )


@router.get("/{run_id}/events/stream")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
):
    async with request.app.state.session_factory() as session:
        await RunService(session).require(run_id)

    async def stream() -> AsyncIterator[str]:
        cursor = last_event_id or 0
        heartbeat_elapsed = 0.0
        poll = request.app.state.settings.event_poll_seconds
        while not await request.is_disconnected():
            async with request.app.state.session_factory() as session:
                repository = RunRepository(session)
                events = await repository.events(run_id, after_id=cursor, limit=250)
                run = await repository.get(run_id)
            for event in events:
                cursor = event.id
                body = RunEventResponse.model_validate(event).model_dump_json()
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {body}\n\n"
            if events:
                heartbeat_elapsed = 0.0
            else:
                heartbeat_elapsed += poll
                if (
                    heartbeat_elapsed
                    >= request.app.state.settings.event_heartbeat_seconds
                ):
                    yield ": heartbeat\n\n"
                    heartbeat_elapsed = 0.0
                if run is not None and run.status in TERMINAL_RUN_STATUSES:
                    break
            await asyncio.sleep(poll)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/artifacts", response_model=list[ArtifactResponse])
async def get_run_artifacts(run_id: UUID, session: AsyncSession = Depends(get_session)):
    await RunService(session).require(run_id)
    return await RunRepository(session).artifacts(run_id)


@router.post("/{run_id}/cancel", response_model=ActionResponse)
async def cancel_run(run_id: UUID, session: AsyncSession = Depends(get_session)):
    run = await RunService(session).cancel(run_id)
    return ActionResponse(
        run_id=run.id, status=run.status, message="Cancellation recorded"
    )


@router.post(
    "/{run_id}/resume",
    response_model=ActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_run(run_id: UUID, session: AsyncSession = Depends(get_session)):
    run = await RunService(session).resume(run_id)
    return ActionResponse(
        run_id=run.id, status=run.status, message="Run queued for resume"
    )


@router.post(
    "/{run_id}/retry", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED
)
async def retry_run(run_id: UUID, session: AsyncSession = Depends(get_session)):
    source = await RunService(session).require(run_id)
    project = await ProjectService(session).require(source.project_id)
    command = CreateRunCommand(
        request=source.request,
        target_stack=source.target_stack,
        clarification_gate_enabled=source.clarification_gate_enabled,
    )
    run, _ = await RunService(session).create(project, command, retry_of_id=source.id)
    return run
