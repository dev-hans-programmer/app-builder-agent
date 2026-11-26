from __future__ import annotations

import anyio
from fastapi import APIRouter, Request, Response, status
from kombu import Connection
from redis.asyncio import Redis
from sqlalchemy import text

from src.control_plane.api.contracts import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok", checks={"process": "ok"})


def _rabbit_check(broker_url: str) -> None:
    connection = Connection(broker_url, connect_timeout=2)
    try:
        connection.ensure_connection(max_retries=1, timeout=2)
    finally:
        connection.release()


@router.get("/ready", response_model=HealthResponse)
async def ready(request: Request, response: Response) -> HealthResponse:
    checks: dict[str, str] = {}
    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as error:  # health boundary intentionally captures adapters
        checks["postgres"] = type(error).__name__

    redis = Redis.from_url(request.app.state.settings.redis_url)
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as error:
        checks["redis"] = type(error).__name__
    finally:
        await redis.aclose()

    try:
        await anyio.to_thread.run_sync(
            _rabbit_check, request.app.state.settings.broker_url
        )
        checks["rabbitmq"] = "ok"
    except Exception as error:
        checks["rabbitmq"] = type(error).__name__

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=checks)
