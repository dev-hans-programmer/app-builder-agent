"""Transport-neutral commands accepted by control-plane use cases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateProjectCommand:
    name: str
    slug: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class CreateRunCommand:
    request: str
    clarification_gate_enabled: bool = False
    idempotency_key: str | None = None
    execution_mode: str | None = None
