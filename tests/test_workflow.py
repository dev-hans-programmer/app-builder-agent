"""
Unit tests for workflow module.

Tests for parse_input_node, generate_report_node, create_workflow,
and end-to-end workflow execution.
"""

import json
import pytest
from pathlib import Path
from src.graph import (
    BuilderState,
    create_initial_state,
    ensure_workspace_layout,
    parse_input_node,
    generate_report_node,
    create_workflow,
)
from src.agents.requirement_analyst import build_requirement_artifact


class TestParseInputNode:
    """Tests for parse_input_node function."""

    def test_valid_input_passes(self):
        """Test that valid input passes validation."""
        state = create_initial_state("Build API", "test-project")
        result = parse_input_node(state)
        assert len(result["errors"]) == 0

    def test_old_state_defaults_to_both_stacks(self):
        state = create_initial_state("Build API", "test-project")
        state.pop("target_stack")

        result = parse_input_node(state)

        assert result["target_stack"] == "both"

    def test_missing_prompt_adds_error(self):
        """Test that missing user_prompt adds error."""
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
        result = parse_input_node(state)
        assert len(result["errors"]) > 0
        assert any("prompt" in err.lower() for err in result["errors"])

    def test_missing_project_name_adds_error(self):
        """Test that missing project_name adds error."""
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
        result = parse_input_node(state)
        assert len(result["errors"]) > 0
        assert any("project" in err.lower() for err in result["errors"])


class TestGenerateReportNode:
    """Tests for generate_report_node function."""

    def test_creates_reports_directory(self, tmp_path):
        """Test that reports directory is created if missing."""
        state = create_initial_state("Test", "test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["comparison_report"] = "# Test Report"
        result = generate_report_node(state)

        reports_dir = Path(result["artifacts"]["reports_dir"])
        assert reports_dir.exists()
        assert reports_dir.is_dir()

        for file in reports_dir.glob("*"):
            file.unlink()
        reports_dir.rmdir()

    def test_writes_file_with_correct_content(self, tmp_path):
        """Test that report file is written with correct content."""
        state = create_initial_state("Test", "test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["comparison_report"] = "# Test Report\n\nContent here"

        result = generate_report_node(state)

        reports_dir = Path(result["artifacts"]["reports_dir"])
        report_files = list(reports_dir.glob("comparison-*.md"))
        assert len(report_files) > 0

        # Read and verify content
        latest_report = max(report_files, key=lambda path: path.stat().st_mtime)
        content = latest_report.read_text()
        assert "# Test Report" in content
        assert "Content here" in content
        assert "# Delivery Summary" in content
        assert "\n---\n" in content

        assert result["delivery_summary_markdown"]
        assert result["final_checkpoint_path"]

        latest_report.unlink()
        delivery_summary = Path(result["delivery_summary_markdown"])
        if delivery_summary.exists():
            delivery_summary.unlink()
        final_checkpoint = Path(result["final_checkpoint_path"])
        if final_checkpoint.exists():
            final_checkpoint.unlink()

    def test_filename_format_is_correct(self, tmp_path):
        """Test that filename uses timestamped format."""
        state = create_initial_state("Test", "test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["comparison_report"] = "# Report"

        generate_report_node(state)

        reports_dir = Path(state["artifacts"]["reports_dir"])
        report_files = list(reports_dir.glob("comparison-*.md"))
        assert len(report_files) > 0

        # Verify filename pattern
        latest_report = max(report_files, key=lambda path: path.stat().st_mtime)
        assert latest_report.name.startswith("comparison-")
        assert latest_report.name.endswith(".md")

        latest_report.unlink()

    def test_handles_missing_report_gracefully(self, tmp_path):
        """Test that function handles missing comparison_report gracefully."""
        state = create_initial_state("Test", "test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        # Don't set comparison_report

        # Should not raise an exception
        result = generate_report_node(state)
        assert result is not None
        assert result["delivery_summary_markdown"]
        assert not list(Path(result["artifacts"]["reports_dir"]).glob("comparison-*.md"))


class TestCreateWorkflow:
    """Tests for create_workflow function."""

    def test_workflow_is_created(self):
        """Test that workflow is created successfully."""
        workflow = create_workflow()
        assert workflow is not None

    def test_returns_compiled_graph(self):
        """Test that workflow returns a compiled graph."""
        workflow = create_workflow()
        # Should have invoke method
        assert hasattr(workflow, "invoke")


class TestWorkflowExecution:
    """Tests for end-to-end workflow execution."""

    def test_workflow_execution(self, monkeypatch):
        """Test that workflow runs end-to-end."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state(
            "Build a secure API with authentication, a database, and deployment.",
            "test-project",
        )
        workflow = create_workflow()

        final_state = workflow.invoke(state)

        # Verify state fields are present
        assert final_state["user_prompt"] == "Build a secure API with authentication, a database, and deployment."
        assert final_state["project_name"] == "test-project"
        assert "python_output" in final_state
        assert "nodejs_output" in final_state
        assert "comparison_report" in final_state
        assert "execution_plan" in final_state
        assert "execution_trace" in final_state
        assert "verification_results" in final_state
        assert "repair_history" in final_state
        assert "spec_tree" in final_state
        assert final_state["job_status"] == "completed"

    def test_state_flows_through_all_nodes(self, monkeypatch):
        """Test that state flows through all nodes."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state(
            "Build a secure API with authentication, a database, and deployment.",
            "test",
        )
        workflow = create_workflow()

        final_state = workflow.invoke(state)

        # All outputs should be populated by placeholders
        assert final_state["python_output"] is not None
        assert final_state["nodejs_output"] is not None
        assert final_state["comparison_report"] is not None
        assert final_state["execution_plan"] is not None
        assert final_state["execution_trace"] is not None
        assert final_state["verification_results"] is not None
        assert final_state["repair_history"] is not None
        assert final_state["spec_tree"] is not None

    def test_final_state_has_all_outputs(self, monkeypatch):
        """Test that final state contains all expected outputs."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state(
            "Build a secure API with authentication, a database, and deployment.",
            "api-project",
        )
        workflow = create_workflow()

        final_state = workflow.invoke(state)

        # Check all output fields
        assert final_state["python_output"] is not None
        assert final_state["python_output"]["status"] == "placeholder"

        assert final_state["nodejs_output"] is not None
        assert final_state["nodejs_output"]["status"] == "placeholder"

        assert final_state["comparison_report"] is not None
        assert "Comparison Report" in final_state["comparison_report"]
        assert final_state["execution_plan"]["validation_errors"] == []
        assert final_state["execution_trace"]
        assert final_state["verification_results"]
        assert final_state["repair_history"]
        assert final_state["spec_tree"]["validation_errors"] == []
        assert final_state["delivery_summary_markdown"]
        assert final_state["final_checkpoint_path"]

        # Verify no errors
        assert len(final_state["errors"]) == 0

    def test_parallel_execution_completes(self, monkeypatch):
        """Test that parallel execution completes successfully."""
        import time

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state(
            "Build a secure API with authentication, a database, and deployment.",
            "test",
        )
        workflow = create_workflow()

        start = time.time()
        final_state = workflow.invoke(state)
        duration = time.time() - start

        # Should complete quickly since placeholders don't do much
        assert duration < 5.0

        # Both builders should have run
        assert final_state["python_output"] is not None
        assert final_state["nodejs_output"] is not None
        assert final_state["execution_plan"] is not None
        assert final_state["execution_trace"] is not None
        assert final_state["verification_results"] is not None
        assert final_state["repair_history"] is not None

    @pytest.mark.parametrize(
        ("target_stack", "selected_output", "omitted_output"),
        [
            ("python", "python_output", "nodejs_output"),
            ("nodejs", "nodejs_output", "python_output"),
        ],
    )
    def test_single_stack_skips_other_builder_and_comparison(
        self,
        monkeypatch,
        target_stack,
        selected_output,
        omitted_output,
    ):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state(
            "Build a secure API with authentication, a database, and deployment.",
            f"{target_stack}-only-project",
            target_stack=target_stack,
        )

        final_state = create_workflow().invoke(state)

        assert final_state[selected_output]["status"] == "placeholder"
        assert final_state[omitted_output] is None
        assert final_state["comparison_report"] is None
        assert final_state["target_stack"] == target_stack
        assert final_state["job_status"] == "completed"

    def test_workflow_prompts_for_clarification_and_continues(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state("Build API", "needs-clarification")
        monkeypatch.setattr(
            "src.agents.clarification_gate.console.input",
            lambda prompt: "PostgreSQL" if "database" in prompt.lower() else "Yes",
        )
        workflow = create_workflow()

        final_state = workflow.invoke(state)

        assert final_state["job_status"] == "completed"

    def test_workflow_skips_clarification_when_disabled(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state(
            "Build API",
            "needs-clarification",
            clarification_gate_enabled=False,
        )
        workflow = create_workflow()

        final_state = workflow.invoke(state)

        assert final_state["job_status"] == "completed"
        assert final_state["clarification_gate_enabled"] is False
        assert final_state["current_phase"] == "completed"
        assert final_state["spec_tree"] is not None
        assert final_state["requirements"]["needs_clarification"] is True

    def test_workflow_resumes_after_clarification_answers(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        state = create_initial_state("Build API", "resume-project")
        requirements = build_requirement_artifact("Build API", "resume-project")
        state["artifacts"] = state["artifacts"] | {"workspace_root": str(tmp_path.resolve())}
        state["artifacts"] = {
            **state["artifacts"],
            "requirements_dir": str(tmp_path / "requirements"),
            "architecture_dir": str(tmp_path / "architecture"),
            "specs_dir": str(tmp_path / "specs"),
            "plans_dir": str(tmp_path / "plans"),
            "execution_dir": str(tmp_path / "execution"),
            "builds_dir": str(tmp_path / "builds"),
            "verification_dir": str(tmp_path / "verification"),
            "repairs_dir": str(tmp_path / "repairs"),
            "reports_dir": str(tmp_path / "reports"),
            "checkpoints_dir": str(tmp_path / "checkpoints"),
        }
        for directory in (
            "requirements",
            "architecture",
            "specs",
            "plans",
            "execution",
            "builds",
            "verification",
            "repairs",
            "reports",
            "checkpoints",
        ):
            (tmp_path / directory).mkdir(parents=True, exist_ok=True)

        response_path = Path(state["artifacts"]["requirements_dir"]) / "clarification.json"
        response_path.write_text(
            json.dumps(
                {
                    "job_id": state["job_id"],
                    "status": "answered",
                    "responses": [
                        {"question": question, "answer": f"answer-{index}"}
                        for index, question in enumerate(requirements["open_questions"], start=1)
                    ],
                }
            ),
            encoding="utf-8",
        )

        workflow = create_workflow()
        final_state = workflow.invoke(state)

        assert final_state["job_status"] == "completed"
        assert final_state["spec_tree"] is not None
        assert final_state["execution_plan"] is not None
        assert final_state["execution_trace"] is not None
        assert final_state["verification_results"] is not None
        assert final_state["repair_history"] is not None
        assert final_state["requirements"]["clarification_answers"]
