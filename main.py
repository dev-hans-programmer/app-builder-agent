#!/usr/bin/env python3
"""
Dual-Stack Backend Builder Agent

Generates backend applications in both Python (FastAPI) and Node.js (Express)
from a single prompt, then provides intelligent comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from src.graph import (
    create_initial_state,
    create_workflow,
    find_latest_checkpoint,
    load_checkpoint,
    restore_state_from_checkpoint,
)

# Load environment variables from .env file
load_dotenv()

# Create Rich console
console = Console()
INCOMPLETE_JOB_STATUSES = {"initialized", "running", "paused", "blocked"}
STACK_CHOICES = ("python", "nodejs", "both")


def _requested_stacks(target_stack: str) -> tuple[str, ...]:
    """Return the concrete builders selected for a target stack."""
    if target_stack == "python":
        return ("python",)
    if target_stack == "nodejs":
        return ("nodejs",)
    return ("python", "nodejs")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for build, status, and resume flows."""
    parser = argparse.ArgumentParser(
        description="Dual-Stack Backend Builder Agent",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--status",
        nargs="?",
        const=True,
        default=None,
        metavar="CHECKPOINT",
        help="Show job status from the latest checkpoint or a specific checkpoint.",
    )
    group.add_argument(
        "--resume",
        nargs="?",
        const=True,
        default=None,
        metavar="CHECKPOINT",
        help="Resume a job from the latest checkpoint or a specific checkpoint.",
    )
    parser.add_argument(
        "--no-clarification-gate",
        action="store_true",
        help="Disable the clarification pause and continue with assumptions.",
    )
    parser.add_argument(
        "--stack",
        choices=STACK_CHOICES,
        default="both",
        help="Generate Python, Node.js, or both implementations (default: both).",
    )
    return parser.parse_args(argv)


def check_environment() -> bool:
    """
    Check if required environment variables are set.

    Returns:
        bool: True if environment is properly configured, False otherwise
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        console.print()
        console.print(
            Panel(
                "[bold red]❌ OPENAI_API_KEY not found[/bold red]\n\n"
                "Please set your API key in the .env file:\n"
                "[cyan]OPENAI_API_KEY=your_key_here[/cyan]\n\n"
                "Get your API key at: https://platform.openai.com/",
                title="[bold red]Configuration Error[/bold red]",
                border_style="red",
            )
        )
        console.print()
        return False

    return True


def display_banner():
    """Display the application banner with ASCII art and styling."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🤖  Dual-Stack Backend Builder Agent                      ║
║                                                              ║
║   Generate Python (FastAPI) & Node.js (Express) backends    ║
║   from a single prompt                                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    console.print(banner, style="bold cyan")


def get_user_input() -> tuple[str, str]:
    """
    Prompt user for input and validate.

    Returns:
        tuple[str, str]: (user_prompt, project_name)

    Raises:
        SystemExit: If user provides empty input
    """
    console.print()
    console.print("[bold yellow]📝 Let's build your backend![/bold yellow]\n")

    user_prompt = console.input("[bold cyan]What would you like to build?[/bold cyan] ")

    if not user_prompt or not user_prompt.strip():
        console.print(
            "\n[bold red]❌ Error:[/bold red] Please provide a description of what to build."
        )
        sys.exit(1)

    project_name = console.input("[bold cyan]Project name:[/bold cyan] ")

    if not project_name or not project_name.strip():
        console.print("\n[bold red]❌ Error:[/bold red] Please provide a project name.")
        sys.exit(1)

    return user_prompt.strip(), project_name.strip()


def display_phase1_start(target_stack: str = "both"):
    """Display the gated generation pipeline header."""
    selected = _requested_stacks(target_stack)
    builder_lines = []
    if "python" in selected:
        builder_lines.append("• Building Python (FastAPI) backend")
    if "nodejs" in selected:
        builder_lines.append("• Building Node.js (Express) backend")
    if len(selected) == 2:
        builder_lines.append("• Running builders in parallel for maximum speed")
    builder_lines.extend(
        [
            "• Approving acceptance criteria and architecture contracts",
            "• Generating code through executable tasks",
            "• Running quality, repair, and traceability gates",
        ]
    )

    console.print()
    console.print("─" * 70, style="dim")
    console.print()
    console.print(
        Panel(
            "[bold white]Phase 1: Code Generation — Gated Pipeline[/bold white]\n\n"
            + "\n".join(builder_lines),
            title="[bold cyan]🚀 Starting Build[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()


def display_phase2_start():
    """Display Phase 2 header."""
    console.print()
    console.print("─" * 70, style="dim")
    console.print()
    console.print(
        Panel(
            "[bold white]Phase 2: Analysis & Comparison[/bold white]\n\n"
            "• Analyzing generated code\n"
            "• Comparing implementations\n"
            "• Generating detailed report",
            title="[bold cyan]🔍 Comparison Agent[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()


def display_results(final_state: dict[str, Any]):
    """
    Display build results in a formatted table.

    Args:
        final_state: Final workflow state containing build results
    """
    console.print()
    console.print("─" * 70, style="dim")
    console.print()

    table = Table(
        title="[bold cyan]Build Results[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Stack", style="cyan", width=10)
    table.add_column("Status", width=12)
    table.add_column("Build Time", justify="right", width=12)
    table.add_column("Files", justify="right", width=8)
    table.add_column("Output Directory", style="dim", no_wrap=False)

    def _safe_duration(value: Any) -> float:
        return value if isinstance(value, (int, float)) else 0.0

    job_status = final_state.get("job_status", "")
    target_stack = final_state.get("target_stack", "both")
    selected_stacks = _requested_stacks(target_stack)
    quality_stacks = {
        str(item.get("stack")): item
        for item in (final_state.get("quality_results") or {}).get("stacks", [])
        if isinstance(item, dict) and item.get("stack")
    }

    def _stack_succeeded(stack: str, generation_status: str) -> bool:
        quality = quality_stacks.get(stack)
        return generation_status == "success" and (
            quality is None or bool(quality.get("passed"))
        )

    python_output = final_state.get("python_output", {}) or {}
    python_status = python_output.get("status", "unknown")
    python_time = _safe_duration(final_state.get("python_build_time"))
    python_files = python_output.get("file_count", 0)
    python_dir = python_output.get("output_dir", "N/A")

    if _stack_succeeded("python", python_status):
        python_status_icon = "✅ Success"
        python_status_style = "green"
    elif job_status == "paused" and not python_output:
        python_status_icon = "⏸ Paused"
        python_status_style = "yellow"
    else:
        python_status_icon = "❌ Failed"
        python_status_style = "red"

    if "python" in selected_stacks:
        table.add_row(
            "Python",
            f"[{python_status_style}]{python_status_icon}[/{python_status_style}]",
            f"{python_time:.2f}s",
            str(python_files),
            python_dir,
        )

    nodejs_output = final_state.get("nodejs_output", {}) or {}
    nodejs_status = nodejs_output.get("status", "unknown")
    nodejs_time = _safe_duration(final_state.get("nodejs_build_time"))
    nodejs_files = nodejs_output.get("file_count", 0)
    nodejs_dir = nodejs_output.get("output_dir", "N/A")

    if _stack_succeeded("nodejs", nodejs_status):
        nodejs_status_icon = "✅ Success"
        nodejs_status_style = "green"
    elif job_status == "paused" and not nodejs_output:
        nodejs_status_icon = "⏸ Paused"
        nodejs_status_style = "yellow"
    else:
        nodejs_status_icon = "❌ Failed"
        nodejs_status_style = "red"

    if "nodejs" in selected_stacks:
        table.add_row(
            "Node.js",
            f"[{nodejs_status_style}]{nodejs_status_icon}[/{nodejs_status_style}]",
            f"{nodejs_time:.2f}s",
            str(nodejs_files),
            nodejs_dir,
        )

    console.print(table)
    console.print()

    errors = final_state.get("errors", [])
    if errors:
        console.print(
            Panel(
                "\n".join(f"• {error}" for error in errors),
                title="[bold red]⚠️  Errors[/bold red]",
                border_style="red",
            )
        )
        console.print()

    if final_state.get("comparison_report"):
        report_path = (final_state.get("artifacts") or {}).get(
            "reports_dir", "./reports"
        )
        console.print(
            f"[green]✓[/green] Comparison report saved to [cyan]{report_path}[/cyan]"
        )
        console.print()


def display_paused_job_notice(final_state: dict[str, Any]) -> None:
    """Show next steps when the workflow pauses for clarification."""
    requirements = final_state.get("requirements") or {}
    artifact_paths = requirements.get("artifact_paths") or {}
    clarification_request = artifact_paths.get("clarification_request_markdown")
    clarification_response = artifact_paths.get("clarification_response_json")
    open_questions = list(requirements.get("open_questions") or [])

    details = [
        "[bold yellow]Workflow paused for clarification.[/bold yellow]",
        "",
        "Answer the questions in the generated clarification response file, then resume the job.",
    ]
    if open_questions:
        details.extend(["", "Open questions:"])
        details.extend(f"• {question}" for question in open_questions)
    if clarification_request:
        details.extend(
            ["", f"Clarification request: [cyan]{clarification_request}[/cyan]"]
        )
    if clarification_response:
        details.extend(
            ["Clarification response: [cyan]{0}[/cyan]".format(clarification_response)]
        )
    checkpoint_path = final_state.get("checkpoint_path")
    if checkpoint_path:
        details.extend(["", f"Checkpoint: [cyan]{checkpoint_path}[/cyan]"])
    details.extend(
        [
            "",
            "Run [cyan]uv run python main.py[/cyan] again to continue this job.",
        ]
    )

    console.print(
        Panel(
            "\n".join(details),
            title="[bold yellow]Clarification Needed[/bold yellow]",
            border_style="yellow",
        )
    )


def display_report_preview(report_path: Path):
    """
    Display a preview of the comparison report.

    Args:
        report_path: Path to the markdown report file
    """
    try:
        if not report_path.exists():
            return

        content = report_path.read_text(encoding="utf-8")

        preview = content[:1000]
        if len(content) > 1000:
            preview += "\n\n[dim]... (preview truncated)[/dim]"

        markdown = Markdown(preview)
        console.print(
            Panel(
                markdown,
                title="[bold cyan]📊 Report Preview[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print()

    except Exception as e:
        console.print(f"[yellow]⚠️  Could not load report preview: {e}[/yellow]")
        console.print()


def _normalize_checkpoint_arg(checkpoint_arg: Any) -> Optional[str]:
    # argparse uses True when the flag is provided without an explicit value.
    if checkpoint_arg in (None, False):
        return None
    if checkpoint_arg is True:
        return None
    return str(checkpoint_arg)


def resolve_checkpoint_path(
    checkpoint_arg: Any,
    *,
    checkpoints_dir: str | Path = "checkpoints",
) -> Path | None:
    """Resolve an explicit checkpoint or fall back to the most recent one."""
    normalized = _normalize_checkpoint_arg(checkpoint_arg)
    if normalized:
        candidate = Path(normalized).expanduser()
        if candidate.exists():
            if candidate.is_dir():
                project_checkpoint_dir = candidate / "checkpoints"
                latest_in_dir = find_latest_checkpoint(project_checkpoint_dir)
                if latest_in_dir is None:
                    latest_in_dir = find_latest_checkpoint(candidate)
                return latest_in_dir.resolve() if latest_in_dir else None
            return candidate.resolve()
        project_checkpoint_dir = Path("projects") / normalized / "checkpoints"
        if project_checkpoint_dir.exists():
            latest_in_project = find_latest_checkpoint(project_checkpoint_dir)
            if latest_in_project:
                return latest_in_project.resolve()
        fallback = Path(checkpoints_dir) / normalized
        if fallback.exists():
            if fallback.is_dir():
                latest_in_fallback = find_latest_checkpoint(fallback)
                return latest_in_fallback.resolve() if latest_in_fallback else None
            return fallback.resolve()
        return fallback.resolve()

    latest = find_latest_checkpoint(checkpoints_dir)
    if latest is None:
        candidate_files = sorted(
            (
                path
                for path in (
                    list(Path("projects").glob("*/checkpoints/*.json"))
                    + list(Path(".").glob("*/checkpoints/*.json"))
                )
                if path.is_file()
            ),
            key=lambda path: path.stat().st_mtime,
        )
        latest = candidate_files[-1] if candidate_files else None
    return latest.resolve() if latest else None


def find_latest_incomplete_checkpoint(search_root: str | Path = ".") -> Path | None:
    """Find the most recent checkpoint whose job is not finished yet."""
    root = Path(search_root)
    checkpoint_files = sorted(
        (
            path
            for path in (
                list(root.rglob("checkpoints/*.json"))
                + list(root.glob("projects/*/checkpoints/*.json"))
            )
            if path.is_file()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for checkpoint_path in checkpoint_files:
        try:
            checkpoint = load_checkpoint(checkpoint_path)
        except Exception:
            continue
        if str(checkpoint.get("job_status", "")) in INCOMPLETE_JOB_STATUSES:
            return checkpoint_path.resolve()
    return None


def load_state_from_checkpoint_path(checkpoint_path: str | Path) -> dict[str, Any]:
    """Load and restore a workflow state from a checkpoint path."""
    checkpoint = load_checkpoint(checkpoint_path)
    return restore_state_from_checkpoint(checkpoint, checkpoint_path=checkpoint_path)


def build_status_snapshot(
    state: dict[str, Any],
    *,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a normalized status snapshot for CLI output."""
    artifacts = state.get("artifacts") or {}
    resolved_checkpoint = (
        checkpoint_path
        or state.get("checkpoint_path")
        or state.get("checkpoint_ref", "")
    )
    return {
        "job_id": state.get("job_id", ""),
        "run_id": state.get("run_id", ""),
        "project_name": state.get("project_name", ""),
        "target_stack": state.get("target_stack", "both"),
        "current_phase": state.get("current_phase", ""),
        "job_status": state.get("job_status", ""),
        "checkpoint_path": str(resolved_checkpoint),
        "requirements_dir": artifacts.get("requirements_dir", ""),
        "architecture_dir": artifacts.get("architecture_dir", ""),
        "specs_dir": artifacts.get("specs_dir", ""),
        "plans_dir": artifacts.get("plans_dir", ""),
        "execution_dir": artifacts.get("execution_dir", ""),
        "builds_dir": artifacts.get("builds_dir", ""),
        "verification_dir": artifacts.get("verification_dir", ""),
        "repairs_dir": artifacts.get("repairs_dir", ""),
        "reports_dir": artifacts.get("reports_dir", ""),
        "checkpoints_dir": artifacts.get("checkpoints_dir", ""),
        "run_dir": artifacts.get("run_dir", ""),
        "run_report_path": artifacts.get("run_report_path", ""),
        "timeline_path": artifacts.get("timeline_path", ""),
        "events_path": artifacts.get("events_path", ""),
        "run_summary_path": artifacts.get("run_summary_path", ""),
    }


def display_job_status(
    state: dict[str, Any],
    *,
    checkpoint_path: str | Path | None = None,
) -> None:
    """Render a human-readable status summary for a checkpoint or job state."""
    snapshot = build_status_snapshot(state, checkpoint_path=checkpoint_path)

    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_column("Field", style="cyan", no_wrap=True)
    summary.add_column("Value", style="white")
    summary.add_row("Job ID", snapshot["job_id"] or "N/A")
    summary.add_row("Run ID", snapshot["run_id"] or "N/A")
    summary.add_row("Project", snapshot["project_name"] or "N/A")
    summary.add_row("Target stack", snapshot["target_stack"])
    summary.add_row("Phase", snapshot["current_phase"] or "N/A")
    summary.add_row("Status", snapshot["job_status"] or "N/A")
    summary.add_row("Checkpoint", snapshot["checkpoint_path"] or "N/A")
    console.print(
        Panel(
            summary,
            title="[bold cyan]Job Status[/bold cyan]",
            border_style="cyan",
        )
    )

    paths = Table(title="[bold cyan]Artifact Paths[/bold cyan]", show_header=True)
    paths.add_column("Artifact", style="cyan")
    paths.add_column("Path", style="white")
    for label, key in (
        ("Requirements", "requirements_dir"),
        ("Architecture", "architecture_dir"),
        ("Specs", "specs_dir"),
        ("Plans", "plans_dir"),
        ("Execution", "execution_dir"),
        ("Builds", "builds_dir"),
        ("Verification", "verification_dir"),
        ("Repairs", "repairs_dir"),
        ("Reports", "reports_dir"),
        ("Checkpoints", "checkpoints_dir"),
        ("Run", "run_dir"),
        ("Run report", "run_report_path"),
        ("Timeline", "timeline_path"),
        ("Events", "events_path"),
        ("Machine summary", "run_summary_path"),
    ):
        if snapshot[key]:
            paths.add_row(label, snapshot[key])
    console.print(paths)

    summary_path = Path(snapshot["run_summary_path"])
    if summary_path.is_file():
        try:
            run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            run_summary = {}
        if run_summary:
            observability = Table(show_header=False, box=None, pad_edge=False)
            observability.add_column("Metric", style="cyan", no_wrap=True)
            observability.add_column("Value", style="white")
            observability.add_row("Events", str(run_summary.get("event_count", 0)))
            observability.add_row(
                "Step attempts", str(run_summary.get("step_attempts", 0))
            )
            observability.add_row(
                "Tokens",
                str(
                    int(run_summary.get("input_tokens", 0))
                    + int(run_summary.get("output_tokens", 0))
                ),
            )
            observability.add_row(
                "Estimated cost",
                (
                    str(run_summary["estimated_cost"])
                    if run_summary.get("estimated_cost") is not None
                    else "n/a"
                ),
            )
            console.print(
                Panel(
                    observability,
                    title="[bold cyan]Run Observability[/bold cyan]",
                    border_style="cyan",
                )
            )

            action_items = list(run_summary.get("action_items") or [])
            if action_items:
                actions = Table(title="[bold yellow]Action Items[/bold yellow]")
                actions.add_column("Step", style="cyan")
                actions.add_column("Status")
                actions.add_column("Suggested fix")
                for item in action_items:
                    actions.add_row(
                        str(item.get("step_id", "")),
                        str(item.get("status", "")),
                        str(item.get("suggested_fix", "")),
                    )
                console.print(actions)


def run_workflow_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Invoke the workflow from the provided state."""
    console.print("[dim]Initializing workflow...[/dim]")
    workflow = create_workflow()

    start_time = time.time()
    final_state = workflow.invoke(state)

    final_state["total_time"] = time.time() - start_time
    return final_state


def _run_build_flow(
    *,
    clarification_gate_enabled: bool = True,
    target_stack: str = "both",
) -> int:
    """Interactive build flow used for normal project creation."""
    display_banner()

    if not check_environment():
        return 1

    user_prompt, project_name = get_user_input()

    console.print()
    console.print("[dim]Creating workflow state...[/dim]")
    state = create_initial_state(
        user_prompt=user_prompt,
        project_name=project_name,
        clarification_gate_enabled=clarification_gate_enabled,
        target_stack=target_stack,
    )

    console.print("[dim]Initializing workflow...[/dim]")
    workflow = create_workflow()

    display_phase1_start(target_stack)

    start_time = time.time()
    console.print("[dim]Running workflow...[/dim]")
    final_state = workflow.invoke(state)

    total_time = time.time() - start_time

    display_results(final_state)

    python_time = final_state.get("python_build_time") or 0
    nodejs_time = final_state.get("nodejs_build_time") or 0
    selected_times = [
        python_time if stack == "python" else nodejs_time
        for stack in _requested_stacks(target_stack)
    ]
    slower_step = max(*selected_times, 0.000001)
    efficiency = (slower_step / total_time * 100) if total_time else 0

    timing_lines = []
    if target_stack in {"python", "both"}:
        timing_lines.append(f"[bold white]Python:[/bold white] {python_time:.2f}s")
    if target_stack in {"nodejs", "both"}:
        timing_lines.append(f"[bold white]Node.js:[/bold white] {nodejs_time:.2f}s")
    efficiency_label = (
        "Parallel efficiency" if target_stack == "both" else "Builder share of total"
    )

    console.print(
        Panel(
            f"[bold white]Total Time:[/bold white] {total_time:.2f}s\n"
            + "\n".join(timing_lines)
            + f"\n\n[dim]{efficiency_label}: {efficiency:.1f}%[/dim]",
            title="[bold cyan]⏱️  Performance[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    if final_state.get("job_status") == "completed":
        output_lines = []
        if target_stack in {"python", "both"}:
            output_lines.append(
                f"• [cyan]{(final_state.get('python_output') or {}).get('output_dir', 'N/A')}[/cyan]"
            )
        if target_stack in {"nodejs", "both"}:
            output_lines.append(
                f"• [cyan]{(final_state.get('nodejs_output') or {}).get('output_dir', 'N/A')}[/cyan]"
            )
        quality_report = (final_state.get("quality_results") or {}).get("artifact_path")
        traceability_report = (final_state.get("traceability_result") or {}).get(
            "artifact_path"
        )
        report_lines = [
            line
            for line in (
                f"• Quality: [cyan]{quality_report}[/cyan]" if quality_report else "",
                f"• Traceability: [cyan]{traceability_report}[/cyan]"
                if traceability_report
                else "",
            )
            if line
        ]
        console.print(
            Panel(
                "[bold green]✨ Build complete![/bold green]\n\n"
                "Your backend is ready in:\n"
                + "\n".join(output_lines)
                + "\n\n"
                + (
                    "Verification evidence:\n" + "\n".join(report_lines) + "\n\n"
                    if report_lines
                    else ""
                )
                + "[dim]Next step: review the generated contracts, code, and verification evidence.[/dim]",
                title="[bold green]🎉 Success[/bold green]",
                border_style="green",
            )
        )
        console.print()
    elif final_state.get("job_status") == "paused":
        display_paused_job_notice(final_state)
    else:
        console.print(
            Panel(
                "[bold red]The workflow did not complete successfully.[/bold red]\n\n"
                "Review the error output above, then resume or rerun after fixing the issue.",
                title="[bold red]Incomplete[/bold red]",
                border_style="red",
            )
        )
        console.print()
    return 0 if final_state.get("job_status") in {"completed", "paused"} else 1


def _run_status_flow(checkpoint_arg: Any) -> int:
    """Display the status of a checkpoint without executing the workflow."""
    checkpoint_path = resolve_checkpoint_path(checkpoint_arg)
    if checkpoint_path is None:
        console.print(
            Panel(
                "[bold yellow]No checkpoint files were found yet.[/bold yellow]\n\n"
                "Run a build first or point `--status` at a specific checkpoint file.",
                title="[bold yellow]Status[/bold yellow]",
                border_style="yellow",
            )
        )
        return 1

    state = load_state_from_checkpoint_path(checkpoint_path)
    display_job_status(state, checkpoint_path=checkpoint_path)
    return 0


def _run_resume_flow(checkpoint_arg: Any) -> int:
    """Resume workflow execution from a checkpoint."""
    display_banner()
    checkpoint_path = resolve_checkpoint_path(checkpoint_arg)
    if checkpoint_path is None:
        console.print(
            Panel(
                "[bold red]No checkpoint files were found to resume from.[/bold red]",
                title="[bold red]Resume Failed[/bold red]",
                border_style="red",
            )
        )
        return 1

    console.print(
        Panel(
            f"[bold cyan]Resuming from:[/bold cyan] {checkpoint_path}",
            title="[bold cyan]Resume[/bold cyan]",
            border_style="cyan",
        )
    )

    state = load_state_from_checkpoint_path(checkpoint_path)
    final_state = run_workflow_from_state(state)
    display_results(final_state)
    if final_state.get("comparison_report"):
        report_dir = Path(
            (final_state.get("artifacts") or {}).get("reports_dir", "./reports")
        )
        report_files = sorted(report_dir.glob("comparison-*.md"))
        if report_files:
            display_report_preview(report_files[-1])
    return 0


def _run_auto_flow(
    *,
    clarification_gate_enabled: bool = True,
    target_stack: str = "both",
) -> int:
    """Resume the latest incomplete job if one exists, otherwise start a new build."""
    checkpoint_path = find_latest_incomplete_checkpoint(".")
    if checkpoint_path is None:
        return _run_build_flow(
            clarification_gate_enabled=clarification_gate_enabled,
            target_stack=target_stack,
        )

    display_banner()
    console.print(
        Panel(
            f"[bold cyan]Resuming latest incomplete job:[/bold cyan] {checkpoint_path}",
            title="[bold cyan]Auto Resume[/bold cyan]",
            border_style="cyan",
        )
    )
    state = load_state_from_checkpoint_path(checkpoint_path)
    final_state = run_workflow_from_state(state)
    display_results(final_state)
    if final_state.get("comparison_report"):
        report_dir = Path(
            (final_state.get("artifacts") or {}).get("reports_dir", "./reports")
        )
        report_files = sorted(report_dir.glob("comparison-*.md"))
        if report_files:
            display_report_preview(report_files[-1])

    if final_state.get("job_status") == "paused":
        display_paused_job_notice(final_state)
    elif final_state.get("job_status") != "completed":
        console.print(
            Panel(
                "[bold red]The workflow did not complete successfully.[/bold red]\n\n"
                "Review the output above and run the agent again after making changes.",
                title="[bold red]Incomplete[/bold red]",
                border_style="red",
            )
        )
        console.print()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Main application entry point."""
    try:
        args = parse_args(argv)

        if args.status is not None:
            return _run_status_flow(args.status)

        if args.resume is not None:
            return _run_resume_flow(args.resume)

        return _run_build_flow(
            clarification_gate_enabled=not args.no_clarification_gate,
            target_stack=getattr(args, "stack", "both"),
        )

    except KeyboardInterrupt:
        console.print()
        console.print()
        console.print(
            Panel(
                "[bold yellow]Build cancelled by user[/bold yellow]\n\n"
                "Any partial builds have been saved.",
                title="[bold yellow]⚠️  Interrupted[/bold yellow]",
                border_style="yellow",
            )
        )
        console.print()
        return 130

    except Exception as e:
        console.print()
        console.print()
        console.print(
            Panel(
                f"[bold red]An unexpected error occurred:[/bold red]\n\n"
                f"[red]{str(e)}[/red]\n\n"
                f"[dim]Please check your configuration and try again.[/dim]",
                title="[bold red]❌ Error[/bold red]",
                border_style="red",
            )
        )
        console.print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
