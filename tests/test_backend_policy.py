"""Python-only production policy loading, prompting, planning, and enforcement."""

from pathlib import Path

import pytest

from src.agents.architect import build_architecture_artifact
from src.agents.planner import build_execution_plan
from src.agents.policy_compliance import evaluate_policy_compliance
from src.agents.python_builder import (
    parse_generation_response,
    validate_generation_metadata,
    validate_task_file_scope,
)
from src.graph import create_initial_state, ensure_workspace_layout
from src.policy import load_backend_policy, policy_text_for_task
from src.prompts.python_builder_prompt import create_python_prompt


def _load_policy(tmp_path: Path, monkeypatch) -> dict:
    monkeypatch.delenv("BACKEND_POLICY_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    state = create_initial_state(
        "Build a todo API", "policy-test", target_stack="python"
    )
    state["artifacts"] = ensure_workspace_layout(tmp_path, project_name="policy-test")
    return load_backend_policy(state)["backend_policy"]


def test_policy_is_loaded_exactly_and_snapshotted_for_python(tmp_path, monkeypatch):
    policy = _load_policy(tmp_path, monkeypatch)

    assert policy["enabled"] is True
    assert len(policy["sections"]) == 36
    assert "TECHNOLOGY STACK" in policy["sections"]["1"]["text"]
    assert "Python 3.13+" in policy["sections"]["1"]["text"]
    assert "IMPORTANT ENGINEERING RULES" in policy["sections"]["35"]["text"]
    assert "Never couple business logic to FastAPI" in policy["sections"]["35"]["text"]
    assert (
        Path(policy["artifact_paths"]["policy_snapshot_markdown"]).read_bytes()
        == Path(policy["source_path"]).read_bytes()
    )


def test_policy_is_disabled_for_nodejs_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BACKEND_POLICY_PATH", str(tmp_path / "missing.md"))
    state = create_initial_state("Build an API", "node", target_stack="nodejs")
    state["artifacts"] = ensure_workspace_layout(tmp_path, project_name="node")

    policy = load_backend_policy(state)["backend_policy"]

    assert policy["enabled"] is False
    assert "Node.js-only" in policy["reason"]


def test_python_architecture_tasks_and_prompt_are_policy_bound(tmp_path, monkeypatch):
    policy = _load_policy(tmp_path, monkeypatch)
    requirements = {
        "id": "todo-requirements",
        "summary": "Register, login, and let users manage only their own todos.",
        "functional_requirements": [
            "Register a user",
            "Login a user",
            "Create a todo",
        ],
        "acceptance_criteria": [
            {"id": "AC-001", "requirement": "Register a user", "status": "approved"},
            {"id": "AC-002", "requirement": "Login a user", "status": "approved"},
            {"id": "AC-003", "requirement": "Create a todo", "status": "approved"},
        ],
        "complexity": "medium",
    }
    architecture = build_architecture_artifact(requirements, "todo", policy)
    spec_tree = {
        "epics": [],
        "specs": [
            {
                "id": "SPEC-001",
                "title": "Todo",
                "module_name": "application",
                "acceptance_criteria_ids": ["AC-003"],
            }
        ],
    }
    plan = build_execution_plan(spec_tree, "todo", requirements, architecture, policy)

    assert architecture["python_production"]["policy_sha256"] == policy["sha256"]
    assert [task["kind"] for task in plan["python_tasks"]] == [
        "foundation",
        "platform",
        "authentication",
        "feature",
        "delivery",
    ]
    assert plan["python_tasks"][1]["acceptance_criteria_ids"] == []

    task = plan["python_tasks"][2]
    prompt = create_python_prompt(
        "Build todos",
        "todo",
        task=task,
        requirements=requirements,
        architecture=architecture,
        backend_policy=policy,
    )
    assert policy["sha256"] in prompt
    assert policy_text_for_task(policy, "authentication") in prompt
    assert "Return JSON only" in prompt


def test_structured_generation_metadata_and_path_scope_are_enforced():
    task = {
        "id": "PY-TASK-001",
        "acceptance_criteria_ids": ["AC-001"],
        "policy_rule_ids": ["BP-04"],
        "allowed_paths": ["app/", "tests/", ".python-version", ".env.example"],
    }
    content = """{
      "task_id": "PY-TASK-001",
      "acceptance_criteria_ids": ["AC-001"],
      "policy_rule_ids": ["BP-04"],
      "files": [{"path": "app/main.py", "content": "app = object()\\n"}]
    }"""

    files, metadata = parse_generation_response(content, task)
    validate_generation_metadata(metadata, task)
    validate_task_file_scope(files, task)

    assert files == {"app/main.py": "app = object()\n"}
    validate_task_file_scope(
        {".python-version": "3.13\n", ".env.example": "DATABASE_URL=...\n"},
        task,
    )
    with pytest.raises(ValueError, match="undeclared file"):
        validate_task_file_scope({"Dockerfile": "FROM python"}, task)
    with pytest.raises(ValueError, match="incorrect policy_rule_ids"):
        validate_generation_metadata({**metadata, "policy_rule_ids": ["BP-99"]}, task)


def test_policy_compliance_produces_actionable_findings(tmp_path):
    policy = {
        "enabled": True,
        "id": "python-production-backend",
        "version": "test",
        "sha256": "abc",
    }
    architecture = {
        "api_contracts": [{"path": "/api/v1/auth/login"}],
        "python_production": {
            "conditional_components": [{"component": "redis", "decision": "omit"}]
        },
    }

    result = evaluate_policy_compliance(tmp_path, policy, architecture)

    assert result["passed"] is False
    assert {item["rule_id"] for item in result["violations"]} >= {
        "BP-04",
        "BP-10",
        "BP-17",
        "BP-25",
        "BP-26",
    }
    assert all(item["remediation"] for item in result["violations"])
