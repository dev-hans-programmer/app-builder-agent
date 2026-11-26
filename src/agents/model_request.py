"""Shared request settings and diagnostics for model-backed agents."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_MAX_COMPLETION_TOKENS = 32_768
_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}


def _is_reasoning_model(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def chat_completion_options(model: str) -> dict[str, Any]:
    """Return model-compatible Chat Completions generation controls."""
    raw_limit = os.getenv(
        "OPENAI_MAX_COMPLETION_TOKENS",
        str(DEFAULT_MAX_COMPLETION_TOKENS),
    )
    try:
        token_limit = int(raw_limit)
    except ValueError as error:
        raise ValueError("OPENAI_MAX_COMPLETION_TOKENS must be an integer") from error
    if token_limit <= 0:
        raise ValueError("OPENAI_MAX_COMPLETION_TOKENS must be greater than zero")

    options: dict[str, Any] = {"max_completion_tokens": token_limit}
    if _is_reasoning_model(model):
        effort = os.getenv("OPENAI_REASONING_EFFORT", "low").strip().lower()
        if effort not in _REASONING_EFFORTS:
            supported = ", ".join(sorted(_REASONING_EFFORTS))
            raise ValueError(
                f"OPENAI_REASONING_EFFORT must be one of: {supported}"
            )
        options["reasoning_effort"] = effort
    return options


def completion_finish_reason(response: Any) -> str | None:
    """Extract the first Chat Completions finish reason, when available."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    choice = choices[0]
    value = (
        choice.get("finish_reason")
        if isinstance(choice, dict)
        else getattr(choice, "finish_reason", None)
    )
    return str(value) if value is not None else None


def require_visible_completion(
    content: str,
    response: Any,
    request_options: dict[str, Any],
) -> None:
    """Raise an actionable error when a model returns no visible content."""
    if content.strip():
        return

    limit = request_options["max_completion_tokens"]
    finish_reason = completion_finish_reason(response)
    usage = getattr(response, "usage", None)
    output_tokens = (
        usage.get("completion_tokens", usage.get("output_tokens", 0))
        if isinstance(usage, dict)
        else getattr(
            usage,
            "completion_tokens",
            getattr(usage, "output_tokens", 0),
        )
    )
    if finish_reason == "length" or output_tokens >= limit:
        raise ValueError(
            "Model exhausted "
            f"max_completion_tokens={limit} before returning visible content. "
            "Increase OPENAI_MAX_COMPLETION_TOKENS or lower "
            "OPENAI_REASONING_EFFORT."
        )
    raise ValueError("Model returned no visible content")
