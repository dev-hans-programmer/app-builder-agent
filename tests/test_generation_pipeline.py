"""Focused tests for the gated generation pipeline."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents import python_builder, quality_gate, targeted_repair
from src.agents.architect import analyze_architecture
from src.agents.planner import plan_execution
from src.agents.requirement_analyst import (
    analyze_requirements,
    approve_acceptance_criteria,
)
from src.agents.spec_generator import generate_specs
from src.agents.traceability import build_traceability_result
from src.graph import create_initial_state, create_workflow, ensure_workspace_layout


def _apply(state: dict, updates: dict) -> dict:
    return {**state, **updates}


def test_planning_artifacts_link_approved_criteria_to_contracts_and_tasks(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    state = create_initial_state(
        "Build a todo API with CRUD operations", "todo", target_stack="python"
    )
    state = _apply(state, analyze_requirements(state))
    state = _apply(state, approve_acceptance_criteria(state))
    state = _apply(state, analyze_architecture(state))
    state = _apply(state, generate_specs(state))
    state = _apply(state, plan_execution(state))

    criterion_ids = {
        item["id"] for item in state["requirements"]["acceptance_criteria"]
    }
    assert criterion_ids
    assert state["requirements"]["acceptance_approval"]["status"] == "approved"
    assert all(
        item["status"] == "approved"
        for item in state["requirements"]["acceptance_criteria"]
    )
    assert all(
        criterion_ids.issubset(set(contract["acceptance_criteria_ids"]))
        for contract in state["architecture_plan"]["api_contracts"]
    )
    assert state["execution_plan"]["tasks"]
    assert all(
        criterion_ids.issubset(set(task["acceptance_criteria_ids"]))
        for task in state["execution_plan"]["tasks"]
    )
    assert Path(
        state["requirements"]["artifact_paths"]["acceptance_criteria_markdown"]
    ).is_file()
    assert Path(
        state["architecture_plan"]["artifact_paths"]["api_contracts_markdown"]
    ).is_file()
    assert Path(
        state["architecture_plan"]["artifact_paths"]["data_contracts_markdown"]
    ).is_file()


def test_python_builder_generates_one_patch_set_per_executable_task(
    tmp_path, monkeypatch
):
    responses = [
        SimpleNamespace(
            id="one",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```filename: main.py\napp = object()\n```"
                    )
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            id="two",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```filename: test_main.py\ndef test_app():\n    assert True\n```"
                    )
                )
            ],
            usage=None,
        ),
    ]
    create = MagicMock(side_effect=responses)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(python_builder, "OpenAI", lambda **kwargs: client)
    state = create_initial_state("Build API", "task-patches", target_stack="python")
    state["artifacts"] = ensure_workspace_layout(tmp_path)
    state["execution_plan"] = {
        "tasks": [
            {
                "id": "TASK-001",
                "acceptance_criteria_ids": ["AC-001"],
                "contract_ids": ["API-001"],
            },
            {
                "id": "TASK-002",
                "acceptance_criteria_ids": ["AC-001"],
                "contract_ids": ["API-001"],
            },
        ]
    }

    result = python_builder.build(state)

    output = result["python_output"]
    assert output["status"] == "success"
    assert create.call_count == 2
    assert [run["task_id"] for run in output["task_runs"]] == ["TASK-001", "TASK-002"]
    assert {patch["path"] for patch in output["patches"]} == {"main.py", "test_main.py"}


def test_generated_path_cannot_escape_build_directory(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        python_builder.apply_file_patches(tmp_path, {"../outside.py": "bad"})
    assert not (tmp_path.parent / "outside.py").exists()


def test_python_quality_gate_runs_required_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("app = object()\n", encoding="utf-8")
    (tmp_path / "test_main.py").write_text(
        "def test_app():\n    assert True\n", encoding="utf-8"
    )
    monkeypatch.setattr(quality_gate.shutil, "which", lambda _name: None)

    result = quality_gate.evaluate_stack(
        "python", {"status": "success", "output_dir": str(tmp_path)}
    )

    checks = {check["category"]: check for check in result["checks"]}
    assert result["passed"] is True
    assert checks["build"]["status"] == "passed"
    assert checks["test"]["status"] == "passed"
    assert checks["smoke"]["status"] == "passed"
    assert checks["lint"]["status"] == "skipped"
    assert checks["type"]["status"] == "skipped"

    state = create_initial_state("Build API", "quality-events", target_stack="python")
    state["python_output"] = {"status": "success", "output_dir": str(tmp_path)}
    updates = quality_gate.run_quality_gate(state)
    events = [
        json.loads(line)
        for line in Path(state["artifacts"]["events_path"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    command_events = [
        event for event in events if event["event_type"] == "quality_check_finished"
    ]
    assert updates["quality_results"]["passed"] is True
    assert {event["verification_check"] for event in command_events} >= {
        "build",
        "test",
        "smoke",
    }
    assert all("command" in event and "exit_code" in event for event in command_events)


def test_production_quality_commands_are_pinned_to_generated_project(
    tmp_path, monkeypatch
):
    generated_root = tmp_path / "projects" / "demo" / "builds" / "python"
    generated_root.mkdir(parents=True)
    monkeypatch.setattr(
        quality_gate.shutil,
        "which",
        lambda name: f"/tools/{name}" if name in {"uv", "docker"} else None,
    )

    definitions = quality_gate._python_commands(generated_root, production_policy=True)
    commands = {
        category: command for category, command, _required, _reason in definitions
    }

    assert commands["dependencies"] == [
        "/tools/uv",
        "lock",
        "--project",
        str(generated_root.resolve()),
    ]
    for category in (
        "build",
        "format_apply",
        "format",
        "lint",
        "type",
        "test",
        "migration",
        "smoke",
    ):
        assert commands[category][:4] == [
            "/tools/uv",
            "run",
            "--project",
            str(generated_root.resolve()),
        ]
    assert commands["container"] is None


def test_quality_environment_isolated_and_container_has_safe_placeholder(
    monkeypatch,
):
    monkeypatch.setenv("VIRTUAL_ENV", "/control-plane/.venv")
    monkeypatch.setenv("DATABASE_PASSWORD", "do-not-forward")
    monkeypatch.setenv("POSTGRES_PASSWORD", "also-do-not-forward")

    regular = quality_gate._safe_environment(category="test")
    container = quality_gate._safe_environment(category="container")

    assert "VIRTUAL_ENV" not in regular
    assert "DATABASE_PASSWORD" not in regular
    assert "POSTGRES_PASSWORD" not in regular
    assert container["POSTGRES_PASSWORD"] == "app_builder_validation_only"


def test_traceability_requires_contract_task_patch_and_quality_evidence():
    state = create_initial_state("Build API", "traceable", target_stack="python")
    state.update(
        {
            "requirements": {
                "acceptance_criteria": [{"id": "AC-001", "requirement": "Create todos"}]
            },
            "architecture_plan": {
                "api_contracts": [
                    {"id": "API-001", "acceptance_criteria_ids": ["AC-001"]}
                ],
                "data_contracts": [],
            },
            "execution_plan": {
                "tasks": [{"id": "TASK-001", "acceptance_criteria_ids": ["AC-001"]}]
            },
            "python_output": {
                "status": "success",
                "patches": [{"path": "main.py"}, {"path": "test_main.py"}],
                "task_runs": [
                    {
                        "task_id": "TASK-001",
                        "acceptance_criteria_ids": ["AC-001"],
                        "patches": [{"path": "main.py"}, {"path": "test_main.py"}],
                    }
                ],
            },
            "quality_results": {
                "status": "passed",
                "passed": True,
                "stacks": [
                    {
                        "stack": "python",
                        "checks": [{"category": "test", "status": "passed"}],
                    }
                ],
            },
        }
    )

    result = build_traceability_result(state)

    assert result["passed"] is True
    assert result["criteria"][0]["status"] == "satisfied"

    state["python_output"]["task_runs"] = []
    failed = build_traceability_result(state)
    assert failed["passed"] is False
    assert "code patch" in failed["criteria"][0]["missing"]


def test_workflow_repairs_failed_quality_gate_and_rechecks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("REQUIREMENTS_MODEL_ENABLED", "false")
    monkeypatch.setattr(quality_gate.shutil, "which", lambda _name: None)

    def without_production_policy(state):
        return {
            "backend_policy": {"enabled": False, "stack": "python"},
            "artifacts": state["artifacts"],
            "current_phase": "policy_loading",
            "job_status": "running",
        }

    monkeypatch.setattr("src.policy.load_backend_policy", without_production_policy)
    generated = SimpleNamespace(
        id="generated",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="```filename: main.py\napp = object()\n```"
                )
            )
        ],
        usage=None,
    )
    repaired = SimpleNamespace(
        id="repaired",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="```filename: test_main.py\ndef test_app():\n    from main import app\n    assert app is not None\n```"
                )
            )
        ],
        usage=None,
    )
    generation_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=MagicMock(return_value=generated))
        )
    )
    repair_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=MagicMock(return_value=repaired))
        )
    )
    monkeypatch.setattr(python_builder, "OpenAI", lambda **_kwargs: generation_client)
    monkeypatch.setattr(targeted_repair, "OpenAI", lambda **_kwargs: repair_client)

    final = create_workflow().invoke(
        create_initial_state(
            "Build a todo API with CRUD operations",
            "repair-loop",
            target_stack="python",
        )
    )

    assert final["repair_attempt"] == 1
    assert final["repair_history"][-1]["status"] == "patched"
    assert len(final["verification_results"]) == 2
    assert final["quality_results"]["status"] == "passed"
    assert final["traceability_result"]["status"] == "passed"
    assert final["job_status"] == "completed"
