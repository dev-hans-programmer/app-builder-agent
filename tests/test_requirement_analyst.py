"""
Tests for the requirement analyst agent.
"""

from pathlib import Path

from src.agents.requirement_analyst import (
    analyze_requirements,
    build_requirement_artifact,
    classify_complexity,
    detect_input_type,
    persist_requirement_artifacts,
    render_requirements_markdown,
)
from src.graph import create_initial_state, ensure_workspace_layout


class TestInputTypeDetection:
    def test_detects_prd(self):
        text = "PRD\n\nGoals\n- Build an API\nNon-goals\n- Frontend"
        assert detect_input_type(text) == "prd"

    def test_detects_feature_list(self):
        text = "Feature List\n- Authentication\n- Payments\nAcceptance Criteria"
        assert detect_input_type(text) == "feature_list"

    def test_detects_brief(self):
        text = "Overview\nRequirements\n1. Build API\n2. Add auth\n3. Add logging"
        assert detect_input_type(text) == "brief"

    def test_defaults_to_prompt(self):
        assert detect_input_type("Build a todo API") == "prompt"


class TestComplexityClassification:
    def test_classifies_simple(self):
        assert classify_complexity("Build a todo API", ["Build a todo API"]) == "simple"

    def test_classifies_medium(self):
        text = "Build a dashboard API with auth and database support"
        assert classify_complexity(text, ["Build dashboard", "Add auth", "Add database"]) == "medium"

    def test_classifies_complex(self):
        text = "Build a microservices platform with payments, queue workers, and websocket updates"
        assert classify_complexity(text, ["a", "b", "c", "d", "e", "f"]) == "complex"


class TestRequirementArtifact:
    def test_build_requirement_artifact_captures_sections(self):
        text = "Build a secure backend API with authentication and a database."
        artifact = build_requirement_artifact(text, "demo-project")

        assert artifact["id"] == "demo-project-requirements"
        assert artifact["title"] == "Requirements for demo-project"
        assert artifact["source_type"] in {"prompt", "brief", "prd", "feature_list"}
        assert artifact["summary"] == text
        assert artifact["functional_requirements"]
        assert "security" in artifact["non_functional_requirements"]
        assert artifact["assumptions"]
        assert artifact["open_questions"]
        assert artifact["complexity"] in {"simple", "medium", "complex"}

    def test_render_requirements_markdown(self):
        artifact = build_requirement_artifact("Build a todo API", "todo")
        markdown = render_requirements_markdown(artifact)

        assert "# Requirements Summary" in markdown
        assert "## Summary" in markdown
        assert "## Open Questions" in markdown

    def test_build_requirement_artifact_captures_constraints(self):
        artifact = build_requirement_artifact("Must use FastAPI for this service.", "service")

        assert "Must use FastAPI" in artifact["constraints"][0]
        assert "Specific implementation stack was mentioned." in artifact["constraints"]


class TestPersistence:
    def test_persist_requirement_artifacts_writes_files(self, tmp_path):
        artifact = build_requirement_artifact("Build a todo API", "todo")
        manifest = ensure_workspace_layout(tmp_path)
        paths = persist_requirement_artifacts(artifact, manifest, "job-123")

        json_path = Path(paths["requirements_json"])
        md_path = Path(paths["requirements_markdown"])

        assert json_path.exists()
        assert md_path.exists()
        assert json_path.read_text(encoding="utf-8")
        assert md_path.read_text(encoding="utf-8")

    def test_persist_requirement_artifacts_writes_questions_file(self, tmp_path):
        artifact = build_requirement_artifact("Build an API", "api")
        artifact["open_questions"] = ["Which database should be used?"]
        manifest = ensure_workspace_layout(tmp_path)
        paths = persist_requirement_artifacts(artifact, manifest, "job-456")

        questions_path = Path(paths["open_questions_markdown"])
        assert questions_path.exists()
        assert "Which database should be used?" in questions_path.read_text(encoding="utf-8")

    def test_persist_requirement_artifacts_removes_stale_questions_file(self, tmp_path):
        artifact = build_requirement_artifact("Build an API with auth, a database, and deployment details.", "api")
        manifest = ensure_workspace_layout(tmp_path)
        stale_questions_path = Path(manifest["requirements_dir"]) / "open-questions.md"

        artifact["open_questions"] = []
        stale_questions_path.write_text("old questions", encoding="utf-8")
        second_paths = persist_requirement_artifacts(artifact, manifest, "job-789")

        assert second_paths["open_questions_markdown"] == ""
        assert not stale_questions_path.exists()

    def test_persist_requirement_artifacts_ignores_clarification_answer_files(self, tmp_path):
        artifact = build_requirement_artifact("Build an API", "api")
        artifact["open_questions"] = []
        artifact["clarification_answers"] = [
            {"question": "Which database or persistence layer should be used?", "answer": "PostgreSQL"},
        ]
        manifest = ensure_workspace_layout(tmp_path)
        paths = persist_requirement_artifacts(artifact, manifest, "job-clarified")

        assert paths["clarification_answers_json"] == ""
        assert paths["clarification_answers_markdown"] == ""
        assert "PostgreSQL" in Path(paths["requirements_json"]).read_text(encoding="utf-8")


class TestAnalyzeRequirements:
    def test_analyze_requirements_updates_state(self, tmp_path):
        state = create_initial_state("Build a secure API with auth", "My Project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)

        result = analyze_requirements(state)

        assert result["job_status"] == "running"
        assert result["current_phase"] == "requirement_analysis"
        assert result["input_type"] in {"prompt", "brief", "prd", "feature_list"}
        assert result["requirements"]["needs_clarification"] in {True, False}
        assert Path(result["requirements"]["artifact_paths"]["requirements_json"]).exists()
