"""
Tests for the execution planning agent.
"""

from pathlib import Path

from src.agents.architect import build_architecture_artifact
from src.agents.planner import (
    build_execution_plan,
    persist_execution_plan_artifacts,
    plan_execution,
    render_execution_plan_markdown,
    validate_execution_plan,
    _parallel_groups,
)
from src.agents.requirement_analyst import build_requirement_artifact
from src.agents.spec_generator import build_spec_tree
from src.graph import create_initial_state, ensure_workspace_layout


class TestExecutionPlanGeneration:
    def test_build_execution_plan_creates_order_and_parallel_groups(self):
        requirements = build_requirement_artifact(
            "Build a secure API with authentication, database access, logging, and deployment.",
            "demo",
        )
        architecture = build_architecture_artifact(requirements, "demo")
        spec_tree = build_spec_tree(requirements, architecture, "demo")

        plan = build_execution_plan(spec_tree, "demo")

        assert plan["id"] == "demo-execution-plan"
        assert plan["ordered_specs"]
        assert plan["parallel_groups"]
        assert plan["checkpoints"]
        assert plan["retry_policy"]["max_attempts_per_spec"] == 2

    def test_build_execution_plan_uses_fallback_checkpoint_when_parallel_groups_missing(self, monkeypatch):
        requirements = build_requirement_artifact(
            "Build a secure API with authentication, database access, logging, and deployment.",
            "demo",
        )
        architecture = build_architecture_artifact(requirements, "demo")
        spec_tree = build_spec_tree(requirements, architecture, "demo")

        monkeypatch.setattr("src.agents.planner._parallel_groups", lambda nodes, ordered: [])
        plan = build_execution_plan(spec_tree, "demo")

        assert plan["checkpoints"] == [f"checkpoint-after-{plan['ordered_specs'][0]}"]

    def test_build_execution_plan_handles_empty_tree(self):
        plan = build_execution_plan({"epics": []}, "demo")

        assert plan["ordered_specs"] == []
        assert plan["parallel_groups"] == []

    def test_render_execution_plan_markdown(self):
        plan = {
            "id": "demo-execution-plan",
            "title": "Execution Plan for demo",
            "ordered_specs": ["epic-1"],
            "parallel_groups": [["epic-1"]],
            "checkpoints": ["checkpoint-after-epic-1"],
            "retry_policy": {"max_attempts_per_spec": 2},
        }

        markdown = render_execution_plan_markdown(plan)

        assert "# Execution Plan" in markdown
        assert "## Ordered Specs" in markdown
        assert "## Parallel Groups" in markdown
        assert "## Checkpoints" in markdown


class TestExecutionPlanPersistence:
    def test_persist_execution_plan_artifacts_writes_files(self, tmp_path):
        plan = {
            "id": "demo-execution-plan",
            "title": "Execution Plan for demo",
            "ordered_specs": ["epic-1"],
            "parallel_groups": [["epic-1"]],
            "checkpoints": ["checkpoint-after-epic-1"],
            "retry_policy": {"max_attempts_per_spec": 2},
        }
        manifest = ensure_workspace_layout(tmp_path)

        paths = persist_execution_plan_artifacts(plan, manifest, "job-400")

        json_path = Path(paths["execution_plan_json"])
        md_path = Path(paths["execution_plan_markdown"])

        assert json_path.exists()
        assert md_path.exists()
        assert "Execution Plan" in md_path.read_text(encoding="utf-8")


class TestExecutionPlanValidation:
    def test_validate_execution_plan_detects_missing_nodes(self):
        spec_tree = {
            "epics": [
                {
                    "id": "epic-1",
                    "title": "Epic",
                    "features": [
                        {
                            "id": "feature-1",
                            "title": "Feature",
                            "components": [
                                {
                                    "id": "component-1",
                                    "title": "Component",
                                    "tasks": [
                                        {
                                            "id": "task-1",
                                            "title": "Task",
                                            "verification_steps": ["verify"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        plan = {
            "ordered_specs": [],
            "dependency_graph": {},
            "parallel_groups": [],
        }

        errors = validate_execution_plan(spec_tree, plan)

        assert any("ordered specs" in err for err in errors)
        assert any("every spec node" in err for err in errors)

    def test_validate_execution_plan_detects_cycle(self):
        spec_tree = {
            "epics": [
                {
                    "id": "epic-1",
                    "title": "Epic",
                    "features": [
                        {
                            "id": "feature-1",
                            "title": "Feature",
                            "components": [
                                {
                                    "id": "component-1",
                                    "title": "Component",
                                    "tasks": [
                                        {
                                            "id": "task-1",
                                            "title": "Task",
                                            "verification_steps": ["verify"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        plan = {
            "ordered_specs": ["epic-1", "feature-1", "component-1", "task-1"],
            "dependency_graph": {
                "epic-1": ["task-1"],
                "feature-1": ["epic-1"],
                "component-1": ["feature-1"],
                "task-1": ["component-1"],
            },
            "parallel_groups": [["epic-1"]],
        }

        errors = validate_execution_plan(spec_tree, plan)

        assert any("cycle" in err for err in errors)

    def test_validate_execution_plan_detects_duplicate_parallel_ids(self):
        spec_tree = {
            "epics": [
                {
                    "id": "epic-1",
                    "title": "Epic",
                    "features": [
                        {
                            "id": "feature-1",
                            "title": "Feature",
                            "components": [
                                {
                                    "id": "component-1",
                                    "title": "Component",
                                    "tasks": [
                                        {
                                            "id": "task-1",
                                            "title": "Task",
                                            "verification_steps": ["verify"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        plan = {
            "ordered_specs": ["epic-1", "feature-1", "component-1", "task-1"],
            "dependency_graph": {},
            "parallel_groups": [["epic-1", "epic-1"]],
        }

        errors = validate_execution_plan(spec_tree, plan)

        assert any("duplicate" in err for err in errors)


class TestParallelGrouping:
    def test_parallel_groups_groups_by_level(self):
        nodes = [
            {"id": "epic-1", "level": "epic"},
            {"id": "feature-1", "level": "feature"},
            {"id": "component-1", "level": "component"},
            {"id": "task-1", "level": "task"},
        ]
        ordered = ["epic-1", "feature-1", "component-1", "task-1"]

        groups = _parallel_groups(nodes, ordered)

        assert groups == [["epic-1"], ["feature-1"], ["component-1"], ["task-1"]]

    def test_parallel_groups_ignores_unknown_levels(self):
        nodes = [{"id": "epic-1", "level": "epic"}]

        groups = _parallel_groups(nodes, ["epic-1", "ghost"])

        assert groups == [["epic-1"]]


class TestPlanExecution:
    def test_plan_execution_updates_state(self, tmp_path):
        state = create_initial_state(
            "Build a secure API with authentication, database access, logging, and deployment.",
            "Demo Project",
        )
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["requirements"] = build_requirement_artifact(
            "Build a secure API with authentication, database access, logging, and deployment.",
            "demo-project",
        )
        state["architecture_plan"] = build_architecture_artifact(state["requirements"], "demo-project")
        state["spec_tree"] = build_spec_tree(state["requirements"], state["architecture_plan"], "demo-project")

        result = plan_execution(state)

        assert result["current_phase"] == "planning"
        assert result["job_status"] == "running"
        assert result["execution_plan"]["artifact_paths"]["execution_plan_json"]
        assert Path(result["execution_plan"]["artifact_paths"]["execution_plan_json"]).exists()
        assert result["execution_plan"]["validation_errors"] == []
