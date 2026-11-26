"""
Tests for the architecture planning agent.
"""

from pathlib import Path

from src.agents.architect import (
    analyze_architecture,
    build_architecture_artifact,
    persist_architecture_artifacts,
    render_architecture_markdown,
    validate_architecture_consistency,
)
from src.agents.requirement_analyst import build_requirement_artifact
from src.graph import create_initial_state, ensure_workspace_layout


class TestArchitectureArtifact:
    def test_build_architecture_artifact_with_database_and_auth(self):
        requirements = build_requirement_artifact(
            "Build a secure API with authentication, database access, logging, and websocket updates.",
            "demo",
        )

        architecture = build_architecture_artifact(requirements, "demo")

        assert architecture["id"] == "demo-architecture"
        assert architecture["title"] == "Architecture for demo"
        assert architecture["source_requirement_id"] == "demo-requirements"
        assert "data" in architecture["module_map"]
        assert "security" in architecture["module_map"]
        assert "observability" in architecture["module_map"]
        assert "transport" in architecture["layers"]
        assert "application" in architecture["layers"]
        assert "domain" in architecture["layers"]
        assert architecture["primary_entities"]
        assert architecture["complexity"] == requirements["complexity"]

    def test_build_architecture_artifact_without_storage(self):
        requirements = {
            "id": "todo-requirements",
            "title": "Requirements for todo",
            "summary": "Build a todo API",
            "functional_requirements": ["Build a todo API"],
            "non_functional_requirements": [],
            "constraints": [],
            "assumptions": [],
            "complexity": "simple",
        }

        architecture = build_architecture_artifact(requirements, "todo")

        assert "transport" in architecture["module_map"]
        assert "application" in architecture["module_map"]
        assert "domain" in architecture["module_map"]
        assert "data" not in architecture["module_map"]
        assert "security" not in architecture["module_map"]
        assert "observability" not in architecture["module_map"]
        assert any(
            item.startswith("Primary entities:") for item in architecture["data_model"]
        )
        assert architecture["primary_entities"]
        assert architecture["rbac_model"] == []

    def test_build_architecture_artifact_with_queue_search_and_production(self):
        requirements = {
            "id": "ops-requirements",
            "title": "Requirements for ops",
            "summary": "Build a queue-driven API with search and production deployment.",
            "functional_requirements": ["Build a queue-driven API", "Support search"],
            "non_functional_requirements": ["production"],
            "constraints": [],
            "assumptions": [],
            "complexity": "medium",
        }

        architecture = build_architecture_artifact(requirements, "ops")

        assert "infrastructure" in architecture["module_map"]
        assert any("search" in item.lower() for item in architecture["api_surface"])
        assert architecture["deployment_notes"]
        assert architecture["service_boundaries"] == [] or any(
            "background" in item.lower() for item in architecture["service_boundaries"]
        )

    def test_render_architecture_markdown(self):
        requirements = build_requirement_artifact(
            "Build a workspace app with users, projects, and auth.",
            "workspace",
        )
        architecture = build_architecture_artifact(requirements, "todo")
        markdown = render_architecture_markdown(architecture)

        assert "# Technical Design" in markdown
        assert "## Domain Model" in markdown
        assert "## Primary Entities" in markdown
        assert "## Module Map" in markdown
        assert "## RBAC Model" in markdown
        assert "## Lifecycle" in markdown
        assert "## Verification Strategy" in markdown
        assert "## Risks" in markdown


class TestArchitecturePersistence:
    def test_persist_architecture_artifacts_writes_files(self, tmp_path):
        requirements = build_requirement_artifact(
            "Build a secure API with authentication and database access.",
            "demo",
        )
        architecture = build_architecture_artifact(requirements, "demo")
        manifest = ensure_workspace_layout(tmp_path)
        paths = persist_architecture_artifacts(architecture, manifest, "job-999")

        json_path = Path(paths["architecture_json"])
        md_path = Path(paths["architecture_markdown"])
        decisions_path = Path(paths["decision_log_markdown"])
        module_map_path = Path(paths["module_map_json"])

        assert json_path.exists()
        assert md_path.exists()
        assert decisions_path.exists()
        assert module_map_path.exists()
        assert "Technical Design" in md_path.read_text(encoding="utf-8")
        assert "Verification Strategy" in md_path.read_text(encoding="utf-8")
        assert "Primary Entities" in md_path.read_text(encoding="utf-8")
        assert "security" in module_map_path.read_text(encoding="utf-8")


class TestConsistencyChecks:
    def test_validate_architecture_consistency_detects_missing_modules(self):
        requirements = build_requirement_artifact(
            "Build an auth-enabled API with database persistence.",
            "demo",
        )
        architecture = build_architecture_artifact(requirements, "demo")
        architecture["module_map"].pop("data", None)
        architecture["module_map"].pop("security", None)

        errors = validate_architecture_consistency(requirements, architecture)

        assert any("data module" in err for err in errors)
        assert any("security module" in err for err in errors)

    def test_validate_architecture_consistency_detects_empty_structure(self):
        requirements = build_requirement_artifact("Build a todo API", "todo")
        architecture = build_architecture_artifact(requirements, "todo")
        architecture["layers"] = []
        architecture["decisions"] = []

        errors = validate_architecture_consistency(requirements, architecture)

        assert "Architecture must define at least one layer." in errors
        assert "Architecture must include decision notes." in errors


class TestAnalyzeArchitecture:
    def test_analyze_architecture_updates_state(self, tmp_path):
        state = create_initial_state(
            "Build a secure API with auth and database", "My Project"
        )
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["requirements"] = build_requirement_artifact(
            "Build a secure API with auth and database",
            "my-project",
        )

        result = analyze_architecture(state)

        assert result["job_status"] == "running"
        assert result["current_phase"] == "architecture_planning"
        assert result["architecture_plan"]["artifact_paths"]["architecture_json"]
        assert Path(
            result["architecture_plan"]["artifact_paths"]["architecture_json"]
        ).exists()
        assert isinstance(result["architecture_plan"]["consistency_errors"], list)
