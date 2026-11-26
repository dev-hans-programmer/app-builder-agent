"""Helpers for normalizing model request metadata and token usage."""

from __future__ import annotations

import hashlib
import os
from typing import Any


def prompt_sha256(prompt: str) -> str:
    """Return a stable hash for a model prompt without logging the prompt itself."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _usage_value(usage: Any, *names: str) -> int:
    for name in names:
        value = (
            usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        )
        if value is not None:
            return _integer(value)
    return 0


def _cached_tokens(usage: Any) -> int:
    details = (
        usage.get("prompt_tokens_details")
        if isinstance(usage, dict)
        else getattr(usage, "prompt_tokens_details", None)
    )
    if details is None:
        details = (
            usage.get("input_tokens_details")
            if isinstance(usage, dict)
            else getattr(usage, "input_tokens_details", None)
        )
    return _usage_value(details, "cached_tokens") if details is not None else 0


def _reasoning_tokens(usage: Any) -> int:
    for name in ("completion_tokens_details", "output_tokens_details"):
        details = (
            usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        )
        if details is not None:
            return _usage_value(details, "reasoning_tokens")
    return 0


def _finish_reason(response: Any | None) -> str | None:
    choices = getattr(response, "choices", None) if response is not None else None
    if not choices:
        return None
    choice = choices[0]
    value = (
        choice.get("finish_reason")
        if isinstance(choice, dict)
        else getattr(choice, "finish_reason", None)
    )
    return str(value) if value is not None else None


def estimate_cost(
    input_tokens: int, output_tokens: int, cached_tokens: int
) -> float | None:
    """Estimate request cost from optional per-million-token environment rates."""
    rate_names = (
        "OPENAI_INPUT_COST_PER_1M",
        "OPENAI_OUTPUT_COST_PER_1M",
        "OPENAI_CACHED_INPUT_COST_PER_1M",
    )
    if not any(os.getenv(name) for name in rate_names):
        return None

    try:
        input_rate = float(os.getenv(rate_names[0], "0"))
        output_rate = float(os.getenv(rate_names[1], "0"))
        cached_rate = float(os.getenv(rate_names[2], "0"))
    except ValueError:
        return None

    uncached_input = max(input_tokens - cached_tokens, 0)
    total = (
        uncached_input * input_rate
        + output_tokens * output_rate
        + cached_tokens * cached_rate
    ) / 1_000_000
    return round(total, 8)


def model_observability(
    *,
    model: str,
    prompt: str,
    prompt_version: str,
    response: Any | None = None,
) -> dict[str, Any]:
    """Build normalized metadata from an OpenAI-compatible response."""
    usage = getattr(response, "usage", None) if response is not None else None
    input_tokens = _usage_value(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_value(usage, "completion_tokens", "output_tokens")
    total_tokens = _usage_value(usage, "total_tokens") or input_tokens + output_tokens
    cached_tokens = _cached_tokens(usage)
    reasoning_tokens = _reasoning_tokens(usage)

    return {
        "model": model,
        "model_request_id": (
            getattr(response, "id", None) if response is not None else None
        ),
        "prompt_version": prompt_version,
        "prompt_hash": prompt_sha256(prompt),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "visible_output_tokens": max(output_tokens - reasoning_tokens, 0),
        "total_tokens": total_tokens,
        "finish_reason": _finish_reason(response),
        "estimated_cost": estimate_cost(input_tokens, output_tokens, cached_tokens),
    }
