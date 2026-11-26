"""
Tests for the spec decomposition agent.
"""

from pathlib import Path

from src.agents.architect import build_architecture_artifact
from src.agents.requirement_analyst import build_requirement_artifact
from src.agents.spec_generator import (
    build_spec_tree,
    generate_specs,
    persist_spec_tree_artifacts,
    render_spec_tree_markdown,
    validate_spec_tree,
)
from src.graph import create_initial_state, ensure_workspace_layout


class TestSpecTreeGeneration:
    def test_build_spec_tree_creates_hierarchy(self):
        requirements = build_requirement_artifact(
            "Build a secure API with authentication, database access, logging, and deployment.",
            "demo",
        )
        architecture = build_architecture_artifact(requirements, "demo")

        spec_tree = build_spec_tree(requirements, architecture, "demo")

        assert spec_tree["id"] == "demo-spec-tree"
        assert spec_tree["epics"]
        assert spec_tree["specs"]
        assert spec_tree["ordered_specs"]
        assert spec_tree["flat_index"]
        assert spec_tree["dependency_graph"]
        assert spec_tree["epics"][0]["features"]
        assert spec_tree["epics"][0]["features"][0]["components"]
        assert spec_tree["epics"][0]["features"][0]["components"][0]["tasks"]
        assert spec_tree["specs"][0]["prompt"]
        assert spec_tree["specs"][0]["tasks"]

    def test_render_spec_tree_markdown_contains_hierarchy(self):
        requirements = build_requirement_artifact(
            "Build API with auth and database", "demo"
        )
        architecture = build_architecture_artifact(requirements, "demo")
        spec_tree = build_spec_tree(requirements, architecture, "demo")

        markdown = render_spec_tree_markdown(spec_tree)

        assert "# Spec Breakdown" in markdown
        assert "## Ordered Specs" in markdown
        assert "specs/" in markdown
        assert "Objective:" in markdown

    def test_build_spec_tree_handles_empty_concerns(self):
        requirements = {
            "id": "demo-requirements",
            "summary": "Build something",
        }
        architecture = {
            "id": "demo-architecture",
            "module_map": {"api": []},
        }

        spec_tree = build_spec_tree(requirements, architecture, "demo")

        assert spec_tree["specs"]
        assert spec_tree["specs"][0]["tasks"]
        assert spec_tree["epics"][0]["features"][0]["components"]


class TestSpecTreePersistence:
    def test_persist_spec_tree_artifacts_writes_files(self, tmp_path):
        requirements = build_requirement_artifact(
            "Build API with auth and database", "demo"
        )
        architecture = build_architecture_artifact(requirements, "demo")
        spec_tree = build_spec_tree(requirements, architecture, "demo")
        manifest = ensure_workspace_layout(tmp_path)

        paths = persist_spec_tree_artifacts(spec_tree, manifest, "job-321")

        json_path = Path(paths["spec_tree_json"])
        md_path = Path(paths["spec_tree_markdown"])
        index_path = Path(paths["spec_index_json"])
        spec_folder = Path(spec_tree["specs"][0]["artifact_paths"]["folder"])
        spec_markdown = Path(spec_tree["specs"][0]["artifact_paths"]["spec_markdown"])
        tasks_markdown = Path(spec_tree["specs"][0]["artifact_paths"]["tasks_markdown"])
        prompt_markdown = Path(
            spec_tree["specs"][0]["artifact_paths"]["prompt_markdown"]
        )

        assert json_path.exists()
        assert md_path.exists()
        assert index_path.exists()
        assert spec_folder.exists()
        assert spec_markdown.exists()
        assert tasks_markdown.exists()
        assert prompt_markdown.exists()
        assert "Spec Breakdown" in md_path.read_text(encoding="utf-8")
        assert "Ordered Specs" in md_path.read_text(encoding="utf-8")


class TestSpecTreeValidation:
    def test_validate_spec_tree_detects_missing_structure(self):
        spec_tree = {"id": "x", "epics": [], "specs": [], "flat_index": []}

        errors = validate_spec_tree(spec_tree)

        assert any("at least one node" in err for err in errors)
        assert any("at least one epic" in err for err in errors)
        assert any("at least one spec" in err for err in errors)

    def test_validate_spec_tree_detects_missing_features(self):
        spec_tree = {
            "id": "x",
            "epics": [
                {
                    "id": "epic-1",
                    "features": [],
                }
            ],
            "flat_index": ["epic-1"],
        }

        errors = validate_spec_tree(spec_tree)

        assert any("must include features" in err for err in errors)

    def test_validate_spec_tree_detects_nested_gaps(self):
        spec_tree = {
            "id": "x",
            "epics": [
                {
                    "id": "epic-1",
                    "features": [
                        {
                            "id": "feature-1",
                            "components": [
                                {
                                    "id": "component-1",
                                    "tasks": [
                                        {
                                            "id": "task-1",
                                            "verification_steps": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "flat_index": ["epic-1", "feature-1", "component-1", "task-1"],
        }

        errors = validate_spec_tree(spec_tree)

        assert any("verification steps" in err for err in errors)

    def test_validate_spec_tree_detects_duplicate_ids(self):
        spec_tree = {
            "id": "x",
            "epics": [
                {
                    "id": "epic-1",
                    "features": [
                        {
                            "id": "feature-1",
                            "components": [
                                {
                                    "id": "component-1",
                                    "tasks": [
                                        {
                                            "id": "task-1",
                                            "verification_steps": ["verify"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "flat_index": ["epic-1", "feature-1", "feature-1", "component-1", "task-1"],
        }

        errors = validate_spec_tree(spec_tree)

        assert any("unique" in err for err in errors)

    def test_validate_spec_tree_detects_missing_children(self):
        spec_tree = {
            "id": "x",
            "epics": [
                {
                    "id": "epic-1",
                    "features": [
                        {
                            "id": "feature-1",
                            "components": [],
                        }
                    ],
                }
            ],
            "flat_index": ["epic-1", "feature-1"],
        }

        errors = validate_spec_tree(spec_tree)

        assert any("must include components" in err for err in errors)

    def test_validate_spec_tree_detects_missing_tasks(self):
        spec_tree = {
            "id": "x",
            "epics": [
                {
                    "id": "epic-1",
                    "features": [
                        {
                            "id": "feature-1",
                            "components": [
                                {
                                    "id": "component-1",
                                    "tasks": [],
                                }
                            ],
                        }
                    ],
                }
            ],
            "flat_index": ["epic-1", "feature-1", "component-1"],
        }

        errors = validate_spec_tree(spec_tree)

        assert any("must include tasks" in err for err in errors)


class TestGenerateSpecs:
    def test_generate_specs_updates_state(self, tmp_path):
        state = create_initial_state("Build API with auth and database", "Demo Project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["requirements"] = build_requirement_artifact(
            "Build API with auth and database", "demo-project"
        )
        state["architecture_plan"] = build_architecture_artifact(
            state["requirements"], "demo-project"
        )

        result = generate_specs(state)

        assert result["current_phase"] == "spec_decomposition"
        assert result["job_status"] == "running"
        assert result["spec_tree"]["artifact_paths"]["spec_tree_json"]
        assert Path(result["spec_tree"]["artifact_paths"]["spec_tree_json"]).exists()
        assert result["spec_tree"]["validation_errors"] == []
        assert result["spec_tree"]["specs"][0]["artifact_paths"]["spec_markdown"]
        assert Path(
            result["spec_tree"]["specs"][0]["artifact_paths"]["prompt_markdown"]
        ).exists()
