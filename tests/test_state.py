"""Tests for Python-only workflow state management."""

from datetime import datetime

from src.graph.state import (
    BuilderState,
    create_initial_state,
    create_job_state,
    sanitize_project_name,
    validate_state,
)


def test_sanitize_project_name() -> None:
    assert sanitize_project_name("My Cool Project!") == "my-cool-project"
    assert sanitize_project_name("Multiple---Hyphens") == "multiple-hyphens"
    assert sanitize_project_name("") == "untitled-project"
    assert len(sanitize_project_name("a" * 100)) == 50


def test_create_initial_state_is_python_only() -> None:
    state = create_initial_state("Build a todo API", "Test Project")

    assert state["project_name"] == "test-project"
    assert state["python_output"] is None
    assert state["python_build_time"] is None
    assert "nodejs_output" not in state
    assert "comparison_report" not in state
    assert "target_stack" not in state
    datetime.fromisoformat(state["timestamp"])
    assert validate_state(state) == []


def test_create_job_state_preserves_input_metadata() -> None:
    state = create_job_state("Build API", "demo", input_type="prd")

    assert state["input_type"] == "prd"
    assert state["raw_request"] == "Build API"


def test_clarification_gate_configuration(monkeypatch) -> None:
    monkeypatch.setenv("CLARIFICATION_GATE_ENABLED", "false")
    assert create_initial_state("Test", "test")["clarification_gate_enabled"] is False
    assert (
        create_initial_state("Test", "test", clarification_gate_enabled=True)[
            "clarification_gate_enabled"
        ]
        is True
    )


def test_validate_state_reports_invalid_required_fields() -> None:
    state = BuilderState(
        user_prompt="",
        project_name="Invalid Name!",
        python_output=None,
        timestamp="invalid",
        errors=[],
        python_build_time=None,
    )

    errors = validate_state(state)

    assert any("user_prompt" in error for error in errors)
    assert any("project_name" in error for error in errors)
    assert any("timestamp" in error for error in errors)


def test_validate_state_checks_structured_fields() -> None:
    state = create_initial_state("Build API", "demo")
    state["clarification_answers"] = []  # type: ignore[assignment]
    state["execution_trace"] = {}  # type: ignore[assignment]

    errors = validate_state(state)

    assert any("clarification_answers" in error for error in errors)
    assert any("execution_trace" in error for error in errors)
