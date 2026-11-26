"""
Tests for the final reporting agent.
"""

from pathlib import Path

from src.agents.final_reporter import build_delivery_summary, persist_delivery_summary
from src.graph import create_initial_state, ensure_workspace_layout


class TestFinalReporter:
    def test_build_delivery_summary_includes_key_sections(self, tmp_path):
        state = create_initial_state("Build API", "demo project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["execution_plan"] = {"ordered_specs": ["spec-1", "spec-2"]}
        state["completed_specs"] = ["spec-1"]
        state["failed_specs"] = []
        state["verification_results"] = [
            {"status": "passed", "failure_category": "none"}
        ]
        state["repair_history"] = [{"status": "completed"}]
        state["python_output"] = {"status": "success"}
        state["nodejs_output"] = {"status": "success"}

        summary = build_delivery_summary(state)

        assert "# Delivery Summary" in summary
        assert "Build Outputs" in summary
        assert "Execution" in summary
        assert "Verification" in summary
        assert "Repair" in summary

    def test_persist_delivery_summary_writes_summary_and_checkpoint(self, tmp_path):
        state = create_initial_state("Build API", "demo project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["job_status"] = "completed"
        state["current_phase"] = "completed"
        state["python_output"] = {"status": "success"}
        state["nodejs_output"] = {"status": "success"}

        result = persist_delivery_summary(state)

        summary_path = Path(result["delivery_summary_markdown"])
        checkpoint_path = Path(result["final_checkpoint_path"])

        assert summary_path.exists()
        assert checkpoint_path.exists()
        assert summary_path.read_text(encoding="utf-8").startswith("# Delivery Summary")

    def test_single_stack_summary_marks_other_stack_not_requested(self, tmp_path):
        state = create_initial_state(
            "Build API",
            "demo project",
            target_stack="python",
        )
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["python_output"] = {"status": "success"}

        summary = build_delivery_summary(state)

        assert "**Target Stack**: python" in summary
        assert "Python output: success" in summary
        assert "Node.js output: not requested" in summary
