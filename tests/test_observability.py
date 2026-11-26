"""Tests for run-scoped workflow observability."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.graph import create_initial_state, create_workflow
from src.agents.python_builder import build as build_python
from src.observability import append_event, instrument_node
from src.observability.model_usage import model_observability


def _events(state):
    path = Path(state["artifacts"]["events_path"])
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_initial_state_creates_run_scoped_observability(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    state = create_initial_state("Build a todo API", "demo")

    run_dir = Path(state["artifacts"]["run_dir"])
    assert run_dir == tmp_path / "projects" / "demo" / "runs" / state["run_id"]
    assert Path(state["artifacts"]["events_path"]).exists()
    assert Path(state["artifacts"]["run_report_path"]).exists()
    assert Path(state["artifacts"]["timeline_path"]).exists()
    assert Path(state["artifacts"]["run_metadata_path"]).exists()
    assert Path(state["artifacts"]["run_summary_path"]).exists()
    assert Path(state["artifacts"]["artifact_manifest_path"]).exists()
    assert Path(state["artifacts"]["run_metadata_path"]).parent.name == "_machine"
    assert "Start here" in Path(state["artifacts"]["run_report_path"]).read_text()

    events = _events(state)
    assert len(events) == 1
    assert events[0]["event_type"] == "run_started"
    assert events[0]["run_id"] == state["run_id"]

    summary = json.loads(Path(state["artifacts"]["run_summary_path"]).read_text())
    assert summary["estimated_cost"] is None

    metadata = json.loads(Path(state["artifacts"]["run_metadata_path"]).read_text())
    assert metadata["request_hash"]
    assert "Build a todo API" not in json.dumps(metadata)


def test_single_stack_workflow_records_end_to_end_trace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    state = create_initial_state(
        "Build a secure API with authentication, a database, and deployment.",
        "observed-project",
    )

    final_state = create_workflow().invoke(state)
    events = _events(final_state)

    required_fields = {
        "run_id",
        "step_id",
        "parent_step_id",
        "spec_id",
        "attempt",
        "status",
        "started_at",
        "ended_at",
        "duration_ms",
        "model",
        "prompt_version",
        "prompt_hash",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "estimated_cost",
        "input_artifacts",
        "output_artifacts",
        "artifact_hashes",
        "command",
        "exit_code",
        "retry_reason",
        "error_type",
        "error_message",
        "stack_trace",
    }
    assert all(required_fields <= event.keys() for event in events)
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["event_type"] == "run_finished"

    finished_steps = {
        event["step_id"]: event
        for event in events
        if event["event_type"] == "step_finished"
    }
    assert "python_builder" in finished_steps
    assert "nodejs_builder" not in finished_steps
    assert "comparison" not in finished_steps
    assert finished_steps["python_builder"]["status"] == "skipped"
    assert finished_steps["python_builder"]["model"] == "gpt-4o-mini"
    assert finished_steps["python_builder"]["prompt_hash"]

    steps_dir = Path(final_state["artifacts"]["steps_dir"])
    python_report = next(steps_dir.glob("*-python-builder.md"))
    python_prompt = next(steps_dir.glob("*-python-builder-prompt.md"))
    assert "Status: **Skipped**" in python_report.read_text()
    assert "exact redacted prompt" in python_prompt.read_text()
    assert not list(steps_dir.rglob("input.json"))
    assert not list(steps_dir.rglob("result.json"))
    readable_content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(final_state["artifacts"]["run_dir"]).rglob("*.md")
    )
    assert state["resume_token"] not in readable_content

    summary = json.loads(Path(final_state["artifacts"]["run_summary_path"]).read_text())
    assert summary["status"] == "failed"
    assert summary["event_count"] == len(events)
    assert any(item["step_id"] == "python_builder" for item in summary["action_items"])
    assert (
        "Python Builder" in Path(final_state["artifacts"]["timeline_path"]).read_text()
    )
    assert (
        "What needs attention"
        in Path(final_state["artifacts"]["run_report_path"]).read_text()
    )

    final_checkpoint = json.loads(
        Path(final_state["final_checkpoint_path"]).read_text()
    )
    assert final_checkpoint["job_status"] == "failed"
    assert final_checkpoint["current_phase"] == "completed"

    manifest = json.loads(
        Path(final_state["artifacts"]["artifact_manifest_path"]).read_text()
    )
    registered_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert str(python_prompt) in registered_paths
    assert str(python_report) in registered_paths


def test_instrumented_failure_records_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = create_initial_state("Build API", "failure-project")

    def failing_node(current_state):
        raise RuntimeError(f"cannot build {current_state['project_name']}")

    observed = instrument_node("failing_node", failing_node, parent_step_id="workflow")
    with pytest.raises(RuntimeError, match="cannot build"):
        observed(state)

    event = _events(state)[-1]
    assert event["event_type"] == "step_finished"
    assert event["status"] == "failed"
    assert event["error_type"] == "RuntimeError"
    assert "cannot build" in event["error_message"]
    assert event["suggested_fix"]
    error_log = next(
        Path(state["artifacts"]["steps_dir"]).glob("*-failing-node-error.log")
    )
    step_report = next(Path(state["artifacts"]["steps_dir"]).glob("*-failing-node.md"))
    assert error_log.exists()
    assert "Recommended action" in step_report.read_text()
    summary = json.loads(Path(state["artifacts"]["run_summary_path"]).read_text())
    assert summary["status"] == "failed"


def test_append_event_is_append_only_and_queue_ready(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKER_ID", "worker-7")
    state = create_initial_state("Build API", "queue-ready")
    state["queue_job_id"] = "queue-123"
    events_path = Path(state["artifacts"]["events_path"])
    original = events_path.read_bytes()

    appended = append_event(
        state, {"event_type": "retry_scheduled", "retry_reason": "timeout"}
    )

    assert events_path.read_bytes().startswith(original)
    assert appended["worker_id"] == "worker-7"
    assert appended["queue_job_id"] == "queue-123"
    assert appended["retry_reason"] == "timeout"


def test_repeated_step_creates_new_attempt_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = create_initial_state("Build API", "retry-project")
    observed = instrument_node(
        "retryable_step", lambda current: {"job_status": "running"}
    )

    observed(state)
    observed(state)

    step_root = Path(state["artifacts"]["steps_dir"])
    assert len(list(step_root.glob("*-retryable-step.md"))) == 1
    assert len(list(step_root.glob("*-retryable-step-attempt-2.md"))) == 1
    attempts = [
        event["attempt"]
        for event in _events(state)
        if event["event_type"] == "step_finished"
        and event["step_id"] == "retryable_step"
    ]
    assert attempts == [1, 2]


def test_model_usage_normalizes_tokens_and_estimates_cost(monkeypatch):
    monkeypatch.setenv("OPENAI_INPUT_COST_PER_1M", "1")
    monkeypatch.setenv("OPENAI_OUTPUT_COST_PER_1M", "2")
    monkeypatch.setenv("OPENAI_CACHED_INPUT_COST_PER_1M", "0.5")
    response = SimpleNamespace(
        id="request-1",
        choices=[SimpleNamespace(finish_reason="stop")],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            prompt_tokens_details=SimpleNamespace(cached_tokens=40),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=8),
        ),
    )

    metadata = model_observability(
        model="test-model",
        prompt="hello",
        prompt_version="1.0",
        response=response,
    )

    assert metadata["model_request_id"] == "request-1"
    assert metadata["input_tokens"] == 100
    assert metadata["output_tokens"] == 20
    assert metadata["cached_tokens"] == 40
    assert metadata["reasoning_tokens"] == 8
    assert metadata["visible_output_tokens"] == 12
    assert metadata["finish_reason"] == "stop"
    assert metadata["estimated_cost"] == 0.00012


def test_model_backed_step_records_response_usage_and_generated_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = SimpleNamespace(
        id="request-42",
        model="test-model",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="""```filename: main.py
print(\"hello\")
```"""
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5),
        ),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response),
        )
    )
    monkeypatch.setattr("src.agents.python_builder.OpenAI", lambda api_key: client)
    state = create_initial_state("Build API", "model-project")

    result = instrument_node("python_builder", build_python, parent_step_id="repair")(
        state
    )

    event = _events(state)[-1]
    steps_dir = Path(state["artifacts"]["steps_dir"])
    assert result["python_output"]["status"] == "success"
    assert event["status"] == "succeeded"
    assert event["model_request_id"] == "request-42"
    assert event["input_tokens"] == 50
    assert event["output_tokens"] == 10
    assert event["cached_tokens"] == 5
    prompt_path = next(steps_dir.glob("*-python-builder-prompt.md"))
    response_path = next(steps_dir.glob("*-python-builder-response.md"))
    assert prompt_path.exists()
    assert response_path.exists()
    assert "Request diagnostics" in response_path.read_text()
    generated_file = Path(result["python_output"]["artifact_paths"][0])
    assert generated_file.exists()
    assert str(generated_file) in event["artifact_hashes"]
