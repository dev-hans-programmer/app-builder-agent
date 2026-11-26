"""
Tests for the clarification gate agent.
"""

import json
from pathlib import Path

from src.agents.clarification_gate import (
    clarify_requirements,
    create_clarification_template,
    load_clarification_responses,
    _merge_clarifications,
    _responses_from_payload,
)
from src.agents.requirement_analyst import build_requirement_artifact
from src.graph import create_initial_state, ensure_workspace_layout


class TestClarificationTemplate:
    def test_create_clarification_template_writes_single_clarification_file(self, tmp_path):
        requirements = build_requirement_artifact("Build an API", "demo")
        manifest = ensure_workspace_layout(tmp_path)

        paths = create_clarification_template(requirements, manifest, "job-100")

        clarification_json = Path(paths["clarification_json"])

        assert clarification_json.exists()
        assert "pending" in clarification_json.read_text(encoding="utf-8")


class TestClarificationResponseLoading:
    def test_load_clarification_responses_supports_template_json(self, tmp_path):
        manifest = ensure_workspace_layout(tmp_path)
        clarification_json = Path(manifest["requirements_dir"]) / "clarification.json"
        clarification_json.write_text(
            json.dumps(
                {
                    "job_id": "job-200",
                    "status": "answered",
                    "responses": [
                        {"question": "Which database or persistence layer should be used?", "answer": "PostgreSQL"},
                        {"question": "Should the backend include authentication and authorization?", "answer": "Yes"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        responses = load_clarification_responses(manifest["requirements_dir"], "job-200")

        assert len(responses) == 2
        assert responses[0]["answer"] == "PostgreSQL"

    def test_load_clarification_responses_ignores_invalid_json(self, tmp_path):
        manifest = ensure_workspace_layout(tmp_path)
        clarification_json = Path(manifest["requirements_dir"]) / "clarification.json"
        clarification_json.write_text("{not valid json}", encoding="utf-8")

        responses = load_clarification_responses(manifest["requirements_dir"], "job-201")

        assert responses == []

    def test_responses_from_payload_supports_answers_key(self):
        responses = _responses_from_payload(
            {
                "answers": [
                    {"question": "Q1", "answer": "A1"},
                ]
            }
        )

        assert responses == [{"question": "Q1", "answer": "A1"}]

    def test_responses_from_payload_supports_plain_mapping(self):
        responses = _responses_from_payload({"Q1": "A1"})

        assert responses == [{"question": "Q1", "answer": "A1"}]


class TestClarificationGate:
    def test_clarify_requirements_prompts_and_continues(self, tmp_path, monkeypatch):
        state = create_initial_state("Build an API", "demo project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["requirements"] = build_requirement_artifact("Build an API", "demo")
        monkeypatch.setattr(
            "src.agents.clarification_gate.console.input",
            lambda prompt: "PostgreSQL" if "database" in prompt.lower() else "Yes",
        )

        result = clarify_requirements(state)

        assert result["job_status"] == "running"
        assert result["current_phase"] == "architecture_planning"
        assert result["requirements"]["needs_clarification"] is False
        assert Path(result["requirements"]["artifact_paths"]["clarification_json"]).exists()

    def test_clarify_requirements_returns_running_when_no_open_questions(self, tmp_path):
        state = create_initial_state("Build an API", "demo project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["requirements"] = build_requirement_artifact("Build a secure API with authentication, a database, and deployment.", "demo")

        result = clarify_requirements(state)

        assert result["job_status"] == "running"
        assert result["current_phase"] == "architecture_planning"

    def test_clarify_requirements_merges_answers_and_continues(self, tmp_path):
        state = create_initial_state("Build an API", "demo project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        requirements = build_requirement_artifact("Build an API", "demo")
        state["requirements"] = requirements

        clarification_path = Path(state["artifacts"]["requirements_dir"]) / "clarification.json"
        clarification_path.write_text(
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

        result = clarify_requirements(state)

        assert result["job_status"] == "running"
        assert result["current_phase"] == "architecture_planning"
        assert result["requirements"]["clarification_answers"]
        assert result["requirements"]["needs_clarification"] is False
        assert result["requirements"]["open_questions"] == []
        assert "answer-1" in Path(result["requirements"]["artifact_paths"]["requirements_markdown"]).read_text(encoding="utf-8")

    def test_clarify_requirements_continues_with_partial_answers(self, tmp_path, monkeypatch):
        state = create_initial_state("Build an API", "demo project")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["requirements"] = build_requirement_artifact("Build an API", "demo")
        monkeypatch.setattr(
            "src.agents.clarification_gate.console.input",
            lambda prompt: "PostgreSQL" if "database" in prompt.lower() else "",
        )

        result = clarify_requirements(state)

        assert result["job_status"] == "running"
        assert result["current_phase"] == "architecture_planning"
        assert result["requirements"]["needs_clarification"] is False

    def test_merge_clarifications_marks_pending_questions(self):
        requirements = {
            "open_questions": ["Q1", "Q2"],
        }
        merged = _merge_clarifications(
            requirements,
            [{"question": "Q1", "answer": "A1"}],
        )

        assert merged["clarification_answers"] == [{"question": "Q1", "answer": "A1"}]
        assert merged["open_questions"] == ["Q2"]
