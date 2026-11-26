"""
Tests for the execution engine agent.
"""

import json
from pathlib import Path

from src.agents.architect import build_architecture_artifact
from src.agents.executor import (
    _safe_resolve_path,
    _find_spec_node,
    execute_spec,
    write_json_safely,
    write_text_safely,
)
from src.agents.planner import build_execution_plan
from src.agents.requirement_analyst import build_requirement_artifact
from src.agents.spec_generator import build_spec_tree
from src.graph import create_initial_state, ensure_workspace_layout


class TestSafeWrites:
    def test_safe_resolve_path_rejects_escape(self, tmp_path):
        try:
            _safe_resolve_path(tmp_path, "../escape.txt")
        except ValueError as exc:
            assert "escapes the workspace root" in str(exc)
        else:
            raise AssertionError("Expected ValueError for path escape")

    def test_write_text_safely_writes_and_skips_unchanged(self, tmp_path):
        result1 = write_text_safely(tmp_path, "nested/file.txt", "hello")
        result2 = write_text_safely(tmp_path, "nested/file.txt", "hello")

        assert result1["created"] is True
        assert result1["changed"] is True
        assert result2["created"] is False
        assert result2["changed"] is False

    def test_write_json_safely_writes_json(self, tmp_path):
        result = write_json_safely(tmp_path, "payload.json", {"hello": "world"})

        assert result["changed"] is True
        assert json.loads(Path(result["path"]).read_text(encoding="utf-8")) == {"hello": "world"}


class TestExecuteSpec:
    def test_execute_spec_writes_trace_and_checkpoint(self, tmp_path):
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

        result = execute_spec(state)

        summary_path = Path(tmp_path) / "execution" / result["current_spec_id"] / "summary.json"
        trace_path = Path(tmp_path) / "plans" / "execution-trace.json"
        checkpoint_path = Path(result["checkpoint_path"])

        assert result["current_phase"] == "execution"
        assert result["job_status"] == "running"
        assert result["execution_trace"]
        assert result["completed_specs"] == [execution_plan["ordered_specs"][0]]
        assert summary_path.exists()
        assert trace_path.exists()
        assert checkpoint_path.exists()
        assert checkpoint_path.name == f"{result['current_spec_id']}.json"

    def test_execute_spec_fails_when_plan_is_empty(self, tmp_path):
        state = create_initial_state("Build API", "demo")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["execution_plan"] = {"ordered_specs": []}

        result = execute_spec(state)

        assert result["job_status"] == "failed"
        assert "Execution plan is empty" in result["errors"][-1]

    def test_execute_spec_fails_when_spec_is_missing(self, tmp_path):
        state = create_initial_state("Build API", "demo")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["execution_plan"] = {"ordered_specs": ["missing-spec"]}
        state["spec_tree"] = {"epics": []}

        result = execute_spec(state)

        assert result["job_status"] == "failed"
        assert "not found in spec tree" in result["errors"][-1]

    def test_find_spec_node_resolves_nested_levels(self):
        spec_tree = {
            "epics": [
                {
                    "id": "epic-1",
                    "title": "Epic",
                    "level": "epic",
                    "features": [
                        {
                            "id": "feature-1",
                            "title": "Feature",
                            "level": "feature",
                            "components": [
                                {
                                    "id": "component-1",
                                    "title": "Component",
                                    "level": "component",
                                    "tasks": [
                                        {
                                            "id": "task-1",
                                            "title": "Task",
                                            "level": "task",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        assert _find_spec_node(spec_tree, "feature-1")["level"] == "feature"
        assert _find_spec_node(spec_tree, "component-1")["level"] == "component"
        assert _find_spec_node(spec_tree, "task-1")["level"] == "task"
        assert _find_spec_node(spec_tree, "missing") is None
