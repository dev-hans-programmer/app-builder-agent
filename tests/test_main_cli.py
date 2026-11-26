"""Tests for the Python-only CLI entrypoint."""

from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

import main as cli
from src.graph import create_initial_state, ensure_workspace_layout


class FakeWorkflow:
    def __init__(self, final_state):
        self.final_state = final_state

    def invoke(self, state):
        self.initial_state = state
        return self.final_state


def test_parse_args_has_no_stack_selection() -> None:
    args = cli.parse_args(["--no-clarification-gate"])
    assert args.no_clarification_gate is True
    assert not hasattr(args, "stack")


def test_parse_args_supports_status_and_resume() -> None:
    assert cli.parse_args(["--status"]).status is True
    assert cli.parse_args(["--resume", "job.json"]).resume == "job.json"


def test_environment_check(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.check_environment() is False
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert cli.check_environment() is True


def test_banner_and_generation_header_are_python_only(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False))

    cli.display_banner()
    cli.display_phase1_start()

    text = output.getvalue()
    assert "Python Project Builder Agent" in text
    assert "Python (FastAPI)" in text
    assert "Node.js" not in text
    assert "Comparison" not in text


def test_display_results_renders_python_quality_failure(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False))
    cli.display_results(
        {
            "job_status": "failed",
            "python_output": {"status": "success", "file_count": 1},
            "quality_results": {
                "passed": False,
                "stacks": [{"stack": "python", "passed": False}],
            },
        }
    )
    assert "Failed" in output.getvalue()


def test_report_preview_handles_markdown(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False))
    report = tmp_path / "report.md"
    report.write_text("# Report", encoding="utf-8")
    cli.display_report_preview(report)
    assert "Report Preview" in output.getvalue()


def test_status_snapshot_and_display(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False))
    state = create_initial_state("Build API", "demo")
    state["artifacts"] = ensure_workspace_layout(tmp_path)
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"event_count": 1}), encoding="utf-8")
    state["artifacts"]["run_summary_path"] = str(summary)

    snapshot = cli.build_status_snapshot(state, checkpoint_path=tmp_path / "job.json")
    assert snapshot["checkpoint_path"].endswith("job.json")
    assert "target_stack" not in snapshot
    cli.display_job_status(state)
    assert "Job Status" in output.getvalue()


def test_build_flow_creates_python_state(monkeypatch) -> None:
    final = create_initial_state("Build API", "demo")
    final["job_status"] = "completed"
    final["python_output"] = {"status": "success", "output_dir": "python"}
    fake = FakeWorkflow(final)
    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "check_environment", lambda: True)
    monkeypatch.setattr(cli, "get_user_input", lambda: ("Build API", "demo"))
    monkeypatch.setattr(cli, "create_workflow", lambda: fake)
    monkeypatch.setattr(cli, "display_phase1_start", lambda: None)
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli.console, "print", lambda *args, **kwargs: None)

    assert cli._run_build_flow() == 0
    assert "target_stack" not in fake.initial_state


def test_main_routes_status_resume_and_build(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda argv=None: SimpleNamespace(
            status=True, resume=None, no_clarification_gate=False
        ),
    )
    monkeypatch.setattr(cli, "_run_status_flow", lambda arg: 0)
    assert cli.main([]) == 0

    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda argv=None: SimpleNamespace(
            status=None, resume=True, no_clarification_gate=False
        ),
    )
    monkeypatch.setattr(cli, "_run_resume_flow", lambda arg: 0)
    assert cli.main([]) == 0

    called = {}
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda argv=None: SimpleNamespace(
            status=None, resume=None, no_clarification_gate=False
        ),
    )
    monkeypatch.setattr(
        cli,
        "_run_build_flow",
        lambda *, clarification_gate_enabled=True: (
            called.update(enabled=clarification_gate_enabled) or 0
        ),
    )
    assert cli.main([]) == 0
    assert called == {"enabled": True}


def test_checkpoint_resolution(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "checkpoints" / "job.json"
    checkpoint.parent.mkdir()
    checkpoint.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "find_latest_checkpoint", lambda directory: checkpoint)
    assert (
        cli.resolve_checkpoint_path(None, checkpoints_dir=checkpoint.parent)
        == checkpoint
    )
