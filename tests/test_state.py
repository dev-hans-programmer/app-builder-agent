"""
Unit tests for state management module.

Tests for BuilderState, create_initial_state, sanitize_project_name, and validate_state.
"""

import pytest
from src.graph import (
    BuilderState,
    create_initial_state,
    sanitize_project_name,
    validate_state,
)


class TestSanitizeProjectName:
    """Tests for sanitize_project_name function."""

    def test_normal_name_with_spaces(self):
        """Test normal names with spaces are converted to hyphens."""
        assert sanitize_project_name("My Cool Project") == "my-cool-project"

    def test_special_characters_removed(self):
        """Test special characters are removed."""
        assert sanitize_project_name("Test@#$App!") == "testapp"

    def test_whitespace_trimmed(self):
        """Test leading/trailing spaces are handled."""
        assert sanitize_project_name("   spaces   ") == "spaces"

    def test_multiple_hyphens_collapsed(self):
        """Test multiple consecutive hyphens are collapsed to one."""
        assert sanitize_project_name("Multiple---Hyphens") == "multiple-hyphens"

    def test_empty_string_returns_default(self):
        """Test empty string returns 'untitled-project'."""
        assert sanitize_project_name("") == "untitled-project"

    def test_only_special_chars_returns_default(self):
        """Test string with only special characters returns default."""
        assert sanitize_project_name("@#$%^&*()") == "untitled-project"

    def test_long_name_truncated(self):
        """Test very long names are truncated to 50 characters."""
        long_name = "a" * 100
        result = sanitize_project_name(long_name)
        assert len(result) == 50
        assert result == "a" * 50

    def test_leading_trailing_hyphens_removed(self):
        """Test leading and trailing hyphens are removed."""
        assert sanitize_project_name("-test-") == "test"

    def test_uppercase_converted_to_lowercase(self):
        """Test uppercase letters are converted to lowercase."""
        assert sanitize_project_name("UPPERCASE") == "uppercase"


class TestCreateInitialState:
    """Tests for create_initial_state function."""

    def test_creates_valid_state(self):
        """Test that create_initial_state returns a valid BuilderState."""
        state = create_initial_state("Build a todo API", "Test Project")

        assert state["user_prompt"] == "Build a todo API"
        assert state["project_name"] == "test-project"  # Should be sanitized
        assert state["python_output"] is None
        assert state["nodejs_output"] is None
        assert state["comparison_report"] is None
        assert isinstance(state["timestamp"], str)
        assert isinstance(state["errors"], list)
        assert len(state["errors"]) == 0
        assert state["python_build_time"] is None
        assert state["nodejs_build_time"] is None
        assert state["clarification_gate_enabled"] is True
        assert state["target_stack"] == "both"

    def test_target_stack_can_be_selected(self):
        state = create_initial_state("Test", "test", target_stack="python")

        assert state["target_stack"] == "python"

    def test_invalid_target_stack_is_rejected(self):
        with pytest.raises(ValueError, match="target_stack"):
            create_initial_state("Test", "test", target_stack="ruby")  # type: ignore[arg-type]

    def test_project_name_is_sanitized(self):
        """Test that project name is automatically sanitized."""
        state = create_initial_state("Test", "My Cool Project!")
        assert state["project_name"] == "my-cool-project"

    def test_timestamp_is_iso_format(self):
        """Test that timestamp is in ISO 8601 format."""
        from datetime import datetime

        state = create_initial_state("Test", "test")
        # Should not raise an exception
        datetime.fromisoformat(state["timestamp"])

    def test_errors_initialized_as_empty_list(self):
        """Test that errors is initialized as empty list."""
        state = create_initial_state("Test", "test")
        assert state["errors"] == []
        assert isinstance(state["errors"], list)

    def test_clarification_gate_can_be_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("CLARIFICATION_GATE_ENABLED", "false")

        state = create_initial_state("Test", "test")

        assert state["clarification_gate_enabled"] is False

    def test_clarification_gate_can_be_overridden_explicitly(self, monkeypatch):
        monkeypatch.setenv("CLARIFICATION_GATE_ENABLED", "true")

        state = create_initial_state(
            "Test",
            "test",
            clarification_gate_enabled=False,
        )

        assert state["clarification_gate_enabled"] is False


class TestValidateState:
    """Tests for validate_state function."""

    def test_valid_state_returns_no_errors(self):
        """Test that a valid state returns no errors."""
        state = create_initial_state("Build API", "test-project")
        errors = validate_state(state)
        assert len(errors) == 0

    def test_empty_user_prompt_caught(self):
        """Test that empty user_prompt is caught."""
        state = BuilderState(
            user_prompt="",
            project_name="test",
            python_output=None,
            nodejs_output=None,
            comparison_report=None,
            timestamp="2026-02-13T10:00:00",
            errors=[],
            python_build_time=None,
            nodejs_build_time=None,
        )
        errors = validate_state(state)
        assert len(errors) > 0
        assert any("user_prompt" in err for err in errors)

    def test_empty_project_name_caught(self):
        """Test that empty project_name is caught."""
        state = BuilderState(
            user_prompt="test",
            project_name="",
            python_output=None,
            nodejs_output=None,
            comparison_report=None,
            timestamp="2026-02-13T10:00:00",
            errors=[],
            python_build_time=None,
            nodejs_build_time=None,
        )
        errors = validate_state(state)
        assert len(errors) > 0
        assert any("project_name" in err for err in errors)

    def test_invalid_project_name_format_caught(self):
        """Test that invalid project_name format is caught."""
        state = BuilderState(
            user_prompt="test",
            project_name="Invalid Name!",
            python_output=None,
            nodejs_output=None,
            comparison_report=None,
            timestamp="2026-02-13T10:00:00",
            errors=[],
            python_build_time=None,
            nodejs_build_time=None,
        )
        errors = validate_state(state)
        assert len(errors) > 0
        assert any("lowercase alphanumeric" in err for err in errors)

    def test_invalid_timestamp_format_caught(self):
        """Test that invalid timestamp format is caught."""
        state = BuilderState(
            user_prompt="test",
            project_name="test",
            python_output=None,
            nodejs_output=None,
            comparison_report=None,
            timestamp="not-a-timestamp",
            errors=[],
            python_build_time=None,
            nodejs_build_time=None,
        )
        errors = validate_state(state)
        assert len(errors) > 0
        assert any("timestamp" in err for err in errors)

    def test_multiple_errors_caught(self):
        """Test that multiple errors are caught simultaneously."""
        state = BuilderState(
            user_prompt="",
            project_name="Invalid Name!",
            python_output=None,
            nodejs_output=None,
            comparison_report=None,
            timestamp="invalid",
            errors=[],
            python_build_time=None,
            nodejs_build_time=None,
        )
        errors = validate_state(state)
        assert (
            len(errors) >= 3
        )  # Should catch empty prompt, invalid name, invalid timestamp

    def test_invalid_clarification_answers_caught(self):
        """Test that clarification answers must be a dictionary."""
        state = create_initial_state("Build API", "test-project")
        state["clarification_answers"] = []  # type: ignore[assignment]

        errors = validate_state(state)

        assert any("clarification_answers" in err for err in errors)

    def test_invalid_target_stack_caught(self):
        state = create_initial_state("Build API", "test-project")
        state["target_stack"] = "ruby"  # type: ignore[assignment]

        errors = validate_state(state)

        assert any("target_stack" in err for err in errors)

    def test_invalid_execution_plan_caught(self):
        """Test that execution plan must be a dictionary."""
        state = create_initial_state("Build API", "test-project")
        state["execution_plan"] = []  # type: ignore[assignment]

        errors = validate_state(state)

        assert any("execution_plan" in err for err in errors)

    def test_invalid_execution_trace_caught(self):
        """Test that execution trace must be a list."""
        state = create_initial_state("Build API", "test-project")
        state["execution_trace"] = {}  # type: ignore[assignment]

        errors = validate_state(state)

        assert any("execution_trace" in err for err in errors)

    def test_invalid_checkpoint_path_caught(self):
        """Test that checkpoint path must be a string."""
        state = create_initial_state("Build API", "test-project")
        state["checkpoint_path"] = []  # type: ignore[assignment]

        errors = validate_state(state)

        assert any("checkpoint_path" in err for err in errors)
