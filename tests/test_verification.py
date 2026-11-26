"""
Tests for the verification and repair agent.
"""

from pathlib import Path

from src.agents.architect import build_architecture_artifact
from src.agents.executor import execute_spec
from src.agents.planner import build_execution_plan
from src.agents.requirement_analyst import build_requirement_artifact
from src.agents.spec_generator import build_spec_tree
from src.agents.verification import (
    build_verification_result,
    classify_failure,
    persist_verification_result,
    repair_execution,
    verify_execution,
)
from src.graph import create_initial_state, ensure_workspace_layout


def _build_executed_state(tmp_path):
    state = create_initial_state(
        "Build a secure API with authentication, database access, logging, and deployment.",
        "Demo Project",
    )
    state["artifacts"] = ensure_workspace_layout(tmp_path)
    requirements = build_requirement_artifact(
        "Build a secure API with authentication, database access, logging, and deployment.",
        "demo-project",
    )
    architecture = build_architecture_artifact(requirements, "demo-project")
    spec_tree = build_spec_tree(requirements, architecture, "demo-project")
    execution_plan = build_execution_plan(spec_tree, "demo-project")

    state["requirements"] = requirements
    state["architecture_plan"] = architecture
    state["spec_tree"] = spec_tree
    state["execution_plan"] = execution_plan
    state["current_spec_id"] = execution_plan["ordered_specs"][0]
    state.update(execute_spec(state))
    return state


class TestFailureClassification:
    def test_classify_failure_categories(self):
        assert classify_failure({"status": "passed"}) == "none"
        assert classify_failure({"status": "failed", "spec_id": "", "missing_artifacts": []}) == "blocked-by-missing-input"
        assert classify_failure({"status": "failed", "spec_id": "x", "missing_artifacts": ["summary.json"]}) == "local"
        assert classify_failure({"status": "failed", "spec_id": "x", "missing_artifacts": ["trace.json"]}) == "environment-related"
        assert classify_failure({"status": "failed", "spec_id": "x", "missing_artifacts": ["checkpoint.json"]}) == "cascading"
        assert classify_failure({"status": "failed", "spec_id": "x", "missing_artifacts": ["other"]}) == "local"


class TestVerificationResult:
    def test_build_verification_result_passes_after_execution(self, tmp_path):
        state = _build_executed_state(tmp_path)

        result = build_verification_result(state)

        assert result["passed"] is True
        assert result["status"] == "passed"
        assert result["failure_category"] == "none"
        assert result["checks"]

    def test_persist_verification_result_writes_files(self, tmp_path):
        state = _build_executed_state(tmp_path)
        manifest = state["artifacts"]
        result = build_verification_result(state)
        paths = persist_verification_result(result, manifest, state["job_id"])

        assert Path(paths["verification_json"]).exists()
        assert Path(paths["verification_markdown"]).exists()


class TestVerifyAndRepair:
    def test_verify_execution_updates_state(self, tmp_path):
        state = _build_executed_state(tmp_path)

        result = verify_execution(state)

        assert result["current_phase"] == "verification"
        assert result["job_status"] == "running"
        assert result["verification_results"]
        assert result["verification_results"][-1]["passed"] is True

    def test_repair_execution_skips_when_latest_verification_passed(self, tmp_path):
        state = _build_executed_state(tmp_path)
        verified = verify_execution(state)

        repaired = repair_execution({**state, **verified})

        assert repaired["current_phase"] == "repair"
        assert repaired["job_status"] == "running"
        assert repaired["repair_history"]
        assert repaired["repair_history"][-1]["status"] == "skipped"

    def test_repair_execution_repairs_missing_summary_and_reverifies(self, tmp_path):
        state = _build_executed_state(tmp_path)
        summary_json = Path(tmp_path) / "execution" / state["current_spec_id"] / "summary.json"
        summary_md = Path(tmp_path) / "execution" / state["current_spec_id"] / "summary.md"
        summary_json.unlink()
        summary_md.unlink()

        repaired = repair_execution(state)

        assert repaired["current_phase"] == "repair"
        assert repaired["job_status"] == "running"
        assert repaired["verification_results"][-1]["passed"] is True
        assert repaired["repair_history"][-1]["status"] == "repaired"
        assert summary_json.exists()
        assert summary_md.exists()

    def test_repair_execution_repairs_trace_and_checkpoint(self, tmp_path):
        state = _build_executed_state(tmp_path)
        trace_json = Path(tmp_path) / "plans" / "execution-trace.json"
        trace_md = Path(tmp_path) / "plans" / "execution-trace.md"
        checkpoint_path = Path(tmp_path) / "checkpoints" / f"{state['current_spec_id']}.json"
        trace_json.unlink()
        trace_md.unlink()
        checkpoint_path.unlink()

        repaired = repair_execution(state)

        assert repaired["job_status"] == "running"
        assert repaired["verification_results"][-1]["passed"] is True
        assert trace_json.exists()
        assert trace_md.exists()
        assert checkpoint_path.exists()

    def test_repair_execution_handles_missing_spec(self, tmp_path):
        state = create_initial_state("Build API", "demo")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["verification_results"] = [{"status": "failed", "spec_id": "", "missing_artifacts": []}]

        result = repair_execution(state)

        assert result["job_status"] == "blocked"
        assert result["repair_history"][-1]["status"] == "blocked"
