"""Versioned HTTP request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None


class ProjectResponse(ApiModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunCreate(ApiModel):
    request: str = Field(min_length=1)
    target_stack: Literal["python", "nodejs", "both"] = "python"
    clarification_gate_enabled: bool = False
    idempotency_key: str | None = Field(default=None, max_length=160)


class RunResponse(ApiModel):
    id: UUID
    project_id: UUID
    retry_of_id: UUID | None
    request: str
    target_stack: str
    clarification_gate_enabled: bool
    status: str
    phase: str
    progress: float
    current_step_id: str | None
    queue_task_id: str | None
    worker_id: str | None
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    cancel_requested_at: datetime | None
    error_type: str | None
    error_message: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    estimated_cost: float
    delivery_status: str
    delivery_error: str | None
    repository_owner: str | None
    repository_name: str | None
    repository_url: str | None
    repository_branch: str | None
    repository_commit_sha: str | None
    repository_commit_url: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunStepResponse(ApiModel):
    id: UUID
    run_id: UUID
    step_id: str
    parent_step_id: str | None
    spec_id: str | None
    task_id: str | None
    attempt: int
    status: str
    model: str | None
    prompt_version: str | None
    prompt_hash: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    estimated_cost: float
    command: str | None
    exit_code: int | None
    retry_reason: str | None
    error_type: str | None
    error_message: str | None
    stack_trace: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: float | None


class RunEventResponse(ApiModel):
    id: int
    run_id: UUID
    step_id: str | None
    event_type: str
    level: str
    status: str | None
    message: str | None
    payload: dict[str, Any]
    occurred_at: datetime


class ArtifactResponse(ApiModel):
    id: UUID
    run_id: UUID
    step_id: str | None
    kind: str
    filename: str
    mime_type: str | None
    sha256: str
    size_bytes: int
    local_available: bool
    local_deleted_at: datetime | None
    created_at: datetime


class ActionResponse(ApiModel):
    run_id: UUID
    status: str
    message: str


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(default_factory=dict)
