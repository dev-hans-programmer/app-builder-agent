"""Tests for comparison-agent model requests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.agents import comparison
from src.graph import create_initial_state


def test_comparison_request_supports_reasoning_models(monkeypatch):
    response = SimpleNamespace(
        id="chatcmpl-test",
        model="test-sol-model",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="# Analysis\nBoth implementations work."
                )
            )
        ],
        usage=None,
    )
    create = MagicMock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6.2-sol")
    monkeypatch.setenv("OPENAI_MAX_COMPLETION_TOKENS", "2345")
    monkeypatch.setattr(comparison, "OpenAI", lambda **kwargs: client)

    state = create_initial_state("Build API", "comparison-request-test")
    state["python_output"] = {
        "status": "success",
        "file_count": 1,
        "files_created": ["main.py"],
    }
    state["nodejs_output"] = {
        "status": "success",
        "file_count": 1,
        "files_created": ["index.js"],
    }

    result = comparison.compare(state)

    assert result["comparison_metadata"]["status"] == "success"
    request = create.call_args.kwargs
    assert request["max_completion_tokens"] == 2345
    assert request["reasoning_effort"] == "low"
    assert "max_tokens" not in request
    assert "temperature" not in request
