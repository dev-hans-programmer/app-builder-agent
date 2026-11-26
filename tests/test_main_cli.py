"""
Tests for the CLI entrypoint.
"""

from io import StringIO
import runpy
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


def test_parse_args_supports_status_and_resume():
    status_args = cli.parse_args(["--status"])
    resume_args = cli.parse_args(["--resume", "checkpoints/job.json"])
    disabled_args = cli.parse_args(["--no-clarification-gate"])
    python_args = cli.parse_args(["--stack", "python"])

    assert status_args.status is True
    assert status_args.resume is None
    assert resume_args.resume == "checkpoints/job.json"
    assert resume_args.status is None
    assert disabled_args.no_clarification_gate is True
    assert disabled_args.stack == "both"
    assert python_args.stack == "python"


def test_check_environment_handles_missing_and_present_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.check_environment() is False

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert cli.check_environment() is True


def test_display_banner_and_phase_headers(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=120))

    cli.display_banner()
    cli.display_phase1_start()
    cli.display_phase2_start()

    text = output.getvalue()
    assert "Dual-Stack Backend Builder Agent" in text
    assert "Phase 1: Code Generation" in text
    assert "Phase 2: Analysis & Comparison" in text


def test_get_user_input_handles_success_and_validation(monkeypatch):
    monkeypatch.setattr(cli.console, "input", lambda prompt: "Build API" if "What" in prompt else "demo")
    assert cli.get_user_input() == ("Build API", "demo")

    monkeypatch.setattr(cli.console, "input", lambda prompt: "   ")
    try:
        cli.get_user_input()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit for empty prompt")


def test_get_user_input_rejects_missing_project_name(monkeypatch):
    responses = iter(["Build API", "   "])
    monkeypatch.setattr(cli.console, "input", lambda prompt: next(responses))

    try:
        cli.get_user_input()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit for empty project name")


def test_display_results_and_report_preview(tmp_path, monkeypatch):
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=140))

    final_state = {
        "python_output": {"status": "success", "file_count": 2, "output_dir": "py"},
        "nodejs_output": {"status": "failed", "file_count": 0, "output_dir": "js"},
        "python_build_time": 1.25,
        "nodejs_build_time": 2.5,
        "errors": ["boom"],
        "comparison_report": "# Report",
    }
    cli.display_results(final_state)

    report_path = tmp_path / "report.md"
    report_path.write_text("# Hello\n" + "x" * 1200, encoding="utf-8")
    cli.display_report_preview(report_path)
    cli.display_report_preview(tmp_path / "missing.md")

    class ExplodingPath:
        def exists(self):
            return True

        def read_text(self, encoding="utf-8"):
            raise RuntimeError("boom")

    cli.display_report_preview(ExplodingPath())
    text = output.getvalue()
    assert "Build Results" in text
    assert "Report Preview" in text
    assert "Could not load report preview" in text


def test_display_results_handles_none_durations(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=140))

    final_state = {
        "python_output": {"status": "success", "file_count": 2, "output_dir": "py"},
        "nodejs_output": {"status": "success", "file_count": 1, "output_dir": "js"},
        "python_build_time": None,
        "nodejs_build_time": None,
        "errors": [],
        "comparison_report": "# Report",
    }

    cli.display_results(final_state)

    text = output.getvalue()
    assert "0.00s" in text


def test_build_status_snapshot_includes_artifact_paths(tmp_path):
    state = create_initial_state("Build API", "demo")
    state["artifacts"] = ensure_workspace_layout(tmp_path)

    snapshot = cli.build_status_snapshot(state, checkpoint_path=tmp_path / "checkpoints" / "job.json")

    assert snapshot["checkpoint_path"].endswith("job.json")
    assert snapshot["requirements_dir"].endswith("requirements")
    assert snapshot["reports_dir"].endswith("reports")


def test_resolve_checkpoint_path_supports_explicit_and_latest(tmp_path, monkeypatch):
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    explicit = checkpoint_dir / "job-explicit.json"
    explicit.write_text("{}", encoding="utf-8")

    assert cli.resolve_checkpoint_path(explicit, checkpoints_dir=checkpoint_dir) == explicit.resolve()

    missing = cli.resolve_checkpoint_path("job-missing.json", checkpoints_dir=checkpoint_dir)
    assert missing == (checkpoint_dir / "job-missing.json").resolve()

    fallback = checkpoint_dir / "job-fallback.json"
    fallback.write_text("{}", encoding="utf-8")
    assert cli.resolve_checkpoint_path("job-fallback.json", checkpoints_dir=checkpoint_dir) == fallback.resolve()

    latest = checkpoint_dir / "job-latest.json"
    latest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "find_latest_checkpoint", lambda directory: latest)

    assert cli.resolve_checkpoint_path(None, checkpoints_dir=checkpoint_dir) == latest.resolve()
    assert cli.resolve_checkpoint_path(True, checkpoints_dir=checkpoint_dir) == latest.resolve()


def test_resolve_checkpoint_path_searches_project_workspaces(tmp_path, monkeypatch):
    project_checkpoint = tmp_path / "projects" / "basic-todo" / "checkpoints" / "job-1.json"
    project_checkpoint.parent.mkdir(parents=True)
    project_checkpoint.write_text("{}", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    assert cli.resolve_checkpoint_path(None) == project_checkpoint.resolve()


def test_resolve_checkpoint_path_accepts_project_name(tmp_path, monkeypatch):
    project_checkpoint = tmp_path / "projects" / "error-handler" / "checkpoints" / "job-2.json"
    project_checkpoint.parent.mkdir(parents=True)
    project_checkpoint.write_text("{}", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    assert cli.resolve_checkpoint_path("error-handler") == project_checkpoint.resolve()


def test_run_status_flow_uses_latest_checkpoint(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoints" / "job-1.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cli, "resolve_checkpoint_path", lambda arg: checkpoint_path)
    monkeypatch.setattr(cli, "display_job_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "load_state_from_checkpoint_path", lambda path: {"job_id": "job-1"})

    assert cli._run_status_flow(True) == 0


def test_run_status_flow_reports_missing_checkpoint(monkeypatch):
    monkeypatch.setattr(cli, "resolve_checkpoint_path", lambda arg: None)
    assert cli._run_status_flow(True) == 1


def test_load_state_from_checkpoint_path_round_trip(tmp_path):
    checkpoint_path = tmp_path / "checkpoints" / "job-1.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        """
        {
          "job_id": "job-1",
          "checkpoint_ref": "checkpoint-1",
          "current_phase": "planning",
          "job_status": "paused",
          "state": {
            "job_id": "job-1",
            "project_name": "demo",
            "current_phase": "planning",
            "job_status": "paused",
            "artifacts": {
              "reports_dir": "reports"
            }
          },
          "artifacts": {
            "reports_dir": "reports"
          }
        }
        """,
        encoding="utf-8",
    )

    state = cli.load_state_from_checkpoint_path(checkpoint_path)

    assert state["job_id"] == "job-1"
    assert state["checkpoint_path"].endswith("job-1.json")
    assert state["artifacts"]["reports_dir"] == "reports"


def test_display_job_status_renders_summary(tmp_path, monkeypatch):
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=120))
    state = create_initial_state("Build API", "demo")
    state["artifacts"] = ensure_workspace_layout(tmp_path)

    cli.display_job_status(state, checkpoint_path=tmp_path / "checkpoints" / "job.json")

    text = output.getvalue()
    assert "Job Status" in text
    assert "Artifact Paths" in text


def test_run_workflow_from_state_uses_fake_workflow(monkeypatch):
    final_state = create_initial_state("Build API", "demo")
    fake = FakeWorkflow(final_state)
    monkeypatch.setattr(cli, "create_workflow", lambda: fake)
    monkeypatch.setattr(cli.console, "print", lambda *args, **kwargs: None)

    result = cli.run_workflow_from_state(create_initial_state("Build API", "demo"))

    assert result["total_time"] >= 0


def test_main_as_script_executes_entrypoint(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoints" / "job-1.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        """
        {
          "job_id": "job-1",
          "checkpoint_ref": "checkpoint-1",
          "current_phase": "planning",
          "job_status": "paused",
          "state": {
            "job_id": "job-1",
            "project_name": "demo",
            "current_phase": "planning",
            "job_status": "paused",
            "artifacts": {
              "reports_dir": "reports"
            }
          },
          "artifacts": {
            "reports_dir": "reports"
          }
        }
        """,
        encoding="utf-8",
    )
    argv = cli.sys.argv
    try:
        cli.sys.argv = ["main.py", "--status", str(checkpoint_path)]
        try:
            runpy.run_module("main", run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 0
    finally:
        cli.sys.argv = argv


def test_run_resume_flow_invokes_workflow(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoints" / "job-1.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text("{}", encoding="utf-8")

    final_state = create_initial_state("Build API", "demo")
    final_state["comparison_report"] = "# Comparison Report"
    final_state["python_output"] = {"status": "success", "output_dir": "python"}
    final_state["nodejs_output"] = {"status": "success", "output_dir": "node"}

    monkeypatch.setattr(cli, "resolve_checkpoint_path", lambda arg: checkpoint_path)
    monkeypatch.setattr(cli, "load_state_from_checkpoint_path", lambda path: {"job_id": "job-1"})
    monkeypatch.setattr(cli, "run_workflow_from_state", lambda state: final_state)
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli, "display_report_preview", lambda path: None)
    monkeypatch.setattr(cli, "display_banner", lambda: None)

    assert cli._run_resume_flow(True) == 0


def test_run_resume_flow_reports_missing_checkpoint(monkeypatch):
    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "resolve_checkpoint_path", lambda arg: None)

    assert cli._run_resume_flow(True) == 1


def test_run_build_flow_uses_workflow(monkeypatch):
    final_state = create_initial_state("Build API", "demo")
    final_state["comparison_report"] = "# Comparison Report"
    final_state["python_output"] = {"status": "success", "output_dir": "python"}
    final_state["nodejs_output"] = {"status": "success", "output_dir": "node"}
    fake_workflow = FakeWorkflow(final_state)

    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "check_environment", lambda: True)
    monkeypatch.setattr(cli, "get_user_input", lambda: ("Build API", "demo"))
    monkeypatch.setattr(
        cli,
        "create_initial_state",
        lambda user_prompt, project_name, clarification_gate_enabled=True, target_stack="both": create_initial_state(
            user_prompt,
            project_name,
            clarification_gate_enabled=clarification_gate_enabled,
            target_stack=target_stack,
        ),
    )
    monkeypatch.setattr(cli, "create_workflow", lambda: fake_workflow)
    monkeypatch.setattr(cli, "display_phase1_start", lambda target_stack="both": None)
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli.console, "print", lambda *args, **kwargs: None)

    assert cli._run_build_flow() == 0


def test_run_build_flow_handles_none_outputs(monkeypatch):
    final_state = create_initial_state("Build API", "demo")
    final_state["python_output"] = None
    final_state["nodejs_output"] = None
    fake_workflow = FakeWorkflow(final_state)

    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "check_environment", lambda: True)
    monkeypatch.setattr(cli, "get_user_input", lambda: ("Build API", "demo"))
    monkeypatch.setattr(
        cli,
        "create_initial_state",
        lambda user_prompt, project_name, clarification_gate_enabled=True, target_stack="both": create_initial_state(
            user_prompt,
            project_name,
            clarification_gate_enabled=clarification_gate_enabled,
            target_stack=target_stack,
        ),
    )
    monkeypatch.setattr(cli, "create_workflow", lambda: fake_workflow)
    monkeypatch.setattr(cli, "display_phase1_start", lambda target_stack="both": None)
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli.console, "print", lambda *args, **kwargs: None)

    assert cli._run_build_flow() == 0


def test_run_build_flow_shows_paused_notice(monkeypatch):
    final_state = create_initial_state("Build API", "demo")
    final_state["job_status"] = "paused"
    final_state["requirements"] = {
        "open_questions": ["Which database or persistence layer should be used?"],
        "artifact_paths": {
            "clarification_json": "requirements/clarification.json",
        },
    }
    fake_workflow = FakeWorkflow(final_state)

    output = StringIO()
    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "check_environment", lambda: True)
    monkeypatch.setattr(cli, "get_user_input", lambda: ("Build API", "demo"))
    monkeypatch.setattr(
        cli,
        "create_initial_state",
        lambda user_prompt, project_name, clarification_gate_enabled=True, target_stack="both": create_initial_state(
            user_prompt,
            project_name,
            clarification_gate_enabled=clarification_gate_enabled,
            target_stack=target_stack,
        ),
    )
    monkeypatch.setattr(cli, "create_workflow", lambda: fake_workflow)
    monkeypatch.setattr(cli, "display_phase1_start", lambda target_stack="both": None)
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=140))

    assert cli._run_build_flow() == 0
    text = output.getvalue()
    assert "Workflow paused for clarification" in text
    assert "Clarification Needed" in text


def test_run_build_flow_can_disable_clarification_gate(monkeypatch):
    final_state = create_initial_state("Build API", "demo", clarification_gate_enabled=False)
    final_state["job_status"] = "completed"
    fake_workflow = FakeWorkflow(final_state)

    output = StringIO()
    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "check_environment", lambda: True)
    monkeypatch.setattr(cli, "get_user_input", lambda: ("Build API", "demo"))
    monkeypatch.setattr(cli, "create_initial_state", lambda user_prompt, project_name, clarification_gate_enabled=True, target_stack="both": create_initial_state(user_prompt, project_name, clarification_gate_enabled=clarification_gate_enabled, target_stack=target_stack))
    monkeypatch.setattr(cli, "create_workflow", lambda: fake_workflow)
    monkeypatch.setattr(cli, "display_phase1_start", lambda target_stack="both": None)
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=140))

    assert cli._run_build_flow(clarification_gate_enabled=False) == 0
    assert fake_workflow.initial_state["clarification_gate_enabled"] is False


def test_run_build_flow_stops_when_environment_missing(monkeypatch):
    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(cli, "check_environment", lambda: False)

    assert cli._run_build_flow() == 1


def test_main_status_branch(monkeypatch):
    monkeypatch.setattr(cli, "parse_args", lambda argv=None: SimpleNamespace(status=True, resume=None, no_clarification_gate=False))
    monkeypatch.setattr(cli, "_run_status_flow", lambda arg: 0)

    assert cli.main(["--status"]) == 0


def test_main_resume_branch(monkeypatch):
    monkeypatch.setattr(cli, "parse_args", lambda argv=None: SimpleNamespace(status=None, resume=True, no_clarification_gate=False))
    monkeypatch.setattr(cli, "_run_resume_flow", lambda arg: 0)

    assert cli.main(["--resume"]) == 0


def test_main_build_branch(monkeypatch):
    monkeypatch.setattr(cli, "parse_args", lambda argv=None: SimpleNamespace(status=None, resume=None, no_clarification_gate=False, stack="python"))
    captured = {}
    monkeypatch.setattr(
        cli,
        "_run_build_flow",
        lambda *, clarification_gate_enabled=True, target_stack="both": captured.update(
            clarification_gate_enabled=clarification_gate_enabled,
            target_stack=target_stack,
        ) or 0,
    )

    assert cli.main([]) == 0
    assert captured["target_stack"] == "python"


def test_auto_flow_resumes_latest_incomplete_checkpoint(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "error-handler" / "checkpoints" / "job-1.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        """
        {
          "job_id": "job-1",
          "job_status": "paused",
          "current_phase": "clarification_gate",
          "state": {
            "job_id": "job-1",
            "project_name": "error-handler",
            "job_status": "paused",
            "current_phase": "clarification_gate",
            "artifacts": {
              "reports_dir": "reports"
            }
          }
        }
        """,
        encoding="utf-8",
    )

    final_state = create_initial_state("Build API", "error-handler")
    final_state["job_status"] = "completed"
    final_state["comparison_report"] = "# Report"
    final_state["python_output"] = {"status": "success", "output_dir": "python"}
    final_state["nodejs_output"] = {"status": "success", "output_dir": "node"}
    captured_states = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "display_banner", lambda: None)
    monkeypatch.setattr(
        cli,
        "run_workflow_from_state",
        lambda state: captured_states.append(state) or final_state,
    )
    monkeypatch.setattr(cli, "display_results", lambda state: None)
    monkeypatch.setattr(cli, "display_report_preview", lambda path: None)

    assert cli._run_auto_flow() == 0
    assert captured_states
    assert captured_states[0]["job_id"] == "job-1"


def test_main_keyboard_interrupt_branch(monkeypatch):
    monkeypatch.setattr(cli, "parse_args", lambda argv=None: (_ for _ in ()).throw(KeyboardInterrupt()))

    assert cli.main([]) == 130


def test_main_generic_error_branch(monkeypatch):
    monkeypatch.setattr(cli, "parse_args", lambda argv=None: (_ for _ in ()).throw(RuntimeError("boom")))

    assert cli.main([]) == 1
