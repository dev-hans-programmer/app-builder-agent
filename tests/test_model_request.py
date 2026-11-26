"""Tests for shared model request controls and completion diagnostics."""

from types import SimpleNamespace

import pytest

from src.agents.model_request import (
    DEFAULT_MAX_COMPLETION_TOKENS,
    chat_completion_options,
    require_visible_completion,
)


def test_reasoning_model_defaults_reserve_output_space(monkeypatch):
    monkeypatch.delenv("OPENAI_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)

    options = chat_completion_options("gpt-6.2-sol")

    assert options == {
        "max_completion_tokens": DEFAULT_MAX_COMPLETION_TOKENS,
        "reasoning_effort": "low",
    }


def test_non_reasoning_model_omits_reasoning_effort(monkeypatch):
    monkeypatch.delenv("OPENAI_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "high")

    options = chat_completion_options("gpt-4o-mini")

    assert options == {"max_completion_tokens": DEFAULT_MAX_COMPLETION_TOKENS}


def test_empty_length_limited_completion_has_actionable_error():
    response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="length")],
        usage=SimpleNamespace(completion_tokens=4096),
    )

    with pytest.raises(ValueError, match="exhausted max_completion_tokens=4096"):
        require_visible_completion(
            "",
            response,
            {"max_completion_tokens": 4096, "reasoning_effort": "low"},
        )
