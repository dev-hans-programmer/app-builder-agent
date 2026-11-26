"""Human-readable run reports derived from the canonical event stream."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4


STEP_DESCRIPTIONS = {
    "parse_input": "Validate the request and selected stack.",
    "backend_policy": "Load and snapshot the Python production architecture policy.",
    "requirement_analysis": "Turn the request into explicit requirements and acceptance context.",
    "acceptance_approval": "Freeze the submitted requirements as approved acceptance criteria.",
    "clarification_gate": "Resolve explicitly supplied open questions.",
    "architecture_planning": "Define architecture, contracts, and implementation boundaries.",
    "spec_decomposition": "Break the architecture into executable specifications.",
    "planning": "Order specifications and dependencies for execution.",
    "generation_start": "Start task-level generation for the selected stack or stacks.",
    "quality_gate": "Run build, lint, type, test, and smoke checks on generated code.",
    "targeted_repair": "Repair only the files implicated by failed quality checks.",
    "traceability": "Verify every approved criterion has contract, task, patch, and test evidence.",
    "python_builder": "Generate the FastAPI implementation.",
    "nodejs_builder": "Generate the Express implementation.",
    "comparison": "Compare successful Python and Node.js implementations.",
    "generate_report": "Create the final delivery report and checkpoint.",
}


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)


def step_title(step_id: str) -> str:
    return step_id.replace("_", " ").replace("-", " ").title()


def step_slug(step_id: str) -> str:
    return step_id.replace("_", "-").lower()


def _cell(value: Any) -> str:
    return (
        str(value if value not in (None, "") else "—")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def _relative_path(path: str | Path, run_dir: Path) -> str:
    candidate = Path(path)
    try:
        return os.path.relpath(candidate, run_dir)
    except (OSError, ValueError):
        return str(candidate)


def _relative_link(path: str | Path, run_dir: Path) -> str:
    label = _relative_path(path, run_dir)
    return f"[{label}]({label})"


def _artifact_lines(paths: Sequence[str], run_dir: Path) -> list[str]:
    unique = list(dict.fromkeys(str(path) for path in paths if path))
    if not unique:
        return ["- None"]
    if len(unique) <= 8:
        return [f"- {_relative_link(path, run_dir)}" for path in unique]

    categories = {
        "requirements": "Requirements",
        "architecture": "Architecture",
        "specs": "Specifications",
        "plans": "Plans",
        "execution": "Execution",
        "builds": "Generated code",
        "verification": "Verification",
        "repairs": "Repairs",
        "reports": "Reports",
        "checkpoints": "Checkpoints",
        "steps": "Step diagnostics",
    }
    grouped: dict[str, list[str]] = {}
    for item in unique:
        parts = Path(item).parts
        category = next((part for part in parts if part in categories), "other")
        grouped.setdefault(category, []).append(item)

    lines: list[str] = []
    for category, items in grouped.items():
        label = categories.get(category, "Other artifacts")
        if len(items) == 1:
            lines.append(f"- {label}: {_relative_link(items[0], run_dir)}")
            continue
        common = Path(os.path.commonpath(items))
        if common.is_file():
            common = common.parent
        lines.append(
            f"- {label}: {len(items)} files under {_relative_link(common, run_dir)}"
        )
    return lines


def render_model_artifact(
    filename: str,
    content: Any,
    *,
    step_id: str,
    attempt: int,
) -> str:
    """Render prompts and responses as readable Markdown companion files."""
    title = f"{step_title(step_id)} — Attempt {attempt}"
    if filename == "prompt.txt":
        return "\n".join(
            [
                f"# Model Prompt: {title}",
                "",
                "This is the exact redacted prompt sent to the model.",
                "",
                "## Prompt",
                "",
                str(content),
            ]
        )

    payload = dict(content) if isinstance(content, Mapping) else {"content": content}
    visible_content = str(payload.pop("content", "") or "")
    usage = payload.pop("usage", {})
    lines = [
        f"# Model Response: {title}",
        "",
        "## Request diagnostics",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for key in ("id", "model", "finish_reason"):
        lines.append(f"| {key.replace('_', ' ').title()} | {_cell(payload.get(key))} |")
    if isinstance(usage, Mapping):
        for key in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "visible_output_tokens",
            "cached_tokens",
            "estimated_cost",
        ):
            lines.append(
                f"| {key.replace('_', ' ').title()} | {_cell(usage.get(key))} |"
            )
    lines.extend(
        [
            "",
            "## Visible response",
            "",
            visible_content or "_The model returned no visible content._",
        ]
    )
    return "\n".join(lines)


def write_step_started(
    report_path: Path,
    *,
    step_id: str,
    parent_step_id: str | None,
    attempt: int,
    started_at: str,
    input_artifacts: Sequence[str],
) -> None:
    lines = [
        f"# {step_title(step_id)}",
        "",
        "> Status: **Running**",
        "",
        STEP_DESCRIPTIONS.get(step_id, "Execute this workflow step."),
        "",
        "## Details",
        "",
        f"- Attempt: {attempt}",
        f"- Parent step: {parent_step_id or 'workflow'}",
        f"- Started: {started_at}",
        "",
        "## Inputs",
        "",
        *_artifact_lines(input_artifacts, report_path.parent),
    ]
    _atomic_text(report_path, "\n".join(lines))


def _outcome_summary(
    step_id: str,
    result: Mapping[str, Any],
    status: str,
    error_message: str | None,
) -> str:
    if status in {"failed", "blocked"}:
        return error_message or "The step did not complete successfully."
    if status == "skipped":
        return error_message or "The step was skipped."
    if step_id in {"python_builder", "nodejs_builder"}:
        key = "python_output" if step_id == "python_builder" else "nodejs_output"
        output = result.get(key) if isinstance(result.get(key), Mapping) else {}
        return (
            f"Generated {output.get('file_count', 0)} files in "
            f"{output.get('output_dir', 'the build directory')}."
        )
    if step_id == "requirement_analysis":
        requirements = (
            result.get("requirements")
            if isinstance(result.get("requirements"), Mapping)
            else {}
        )
        return f"Captured {len(requirements.get('functional_requirements', []))} functional requirement(s)."
    if step_id == "verification":
        history = result.get("verification_results") or []
        latest = history[-1] if history and isinstance(history[-1], Mapping) else {}
        return f"Verification status: {latest.get('status', 'completed')}."
    if step_id == "repair":
        history = result.get("repair_history") or []
        latest = history[-1] if history and isinstance(history[-1], Mapping) else {}
        return f"Repair status: {latest.get('status', 'completed')}."
    if step_id == "quality_gate":
        quality = result.get("quality_results") or {}
        return f"Quality gate status: {quality.get('status', 'completed')}."
    if step_id == "targeted_repair":
        history = result.get("repair_history") or []
        latest = history[-1] if history and isinstance(history[-1], Mapping) else {}
        return f"Targeted repair status: {latest.get('status', 'completed')}."
    if step_id == "traceability":
        traceability = result.get("traceability_result") or {}
        return f"Traceability status: {traceability.get('status', 'completed')}."
    return "The step completed successfully."


def write_step_finished(
    report_path: Path,
    *,
    step_id: str,
    parent_step_id: str | None,
    attempt: int,
    status: str,
    started_at: str,
    ended_at: str,
    duration_ms: float,
    input_artifacts: Sequence[str],
    output_artifacts: Sequence[str],
    result: Mapping[str, Any],
    model: Mapping[str, Any],
    error_type: str | None,
    error_message: str | None,
    suggested_fix: str | None,
) -> None:
    lines = [
        f"# {step_title(step_id)}",
        "",
        f"> Status: **{status.title()}**",
        "",
        STEP_DESCRIPTIONS.get(step_id, "Execute this workflow step."),
        "",
        "## Outcome",
        "",
        _outcome_summary(step_id, result, status, error_message),
        "",
        "## Details",
        "",
        f"- Attempt: {attempt}",
        f"- Parent step: {parent_step_id or 'workflow'}",
        f"- Started: {started_at}",
        f"- Ended: {ended_at}",
        f"- Duration: {duration_ms:.1f} ms",
    ]
    if model:
        lines.extend(
            [
                "",
                "## Model usage",
                "",
                "| Field | Value |",
                "|---|---|",
                f"| Model | {_cell(model.get('model'))} |",
                f"| Prompt version | {_cell(model.get('prompt_version'))} |",
                f"| Input tokens | {_cell(model.get('input_tokens', 0))} |",
                f"| Output tokens | {_cell(model.get('output_tokens', 0))} |",
                f"| Reasoning tokens | {_cell(model.get('reasoning_tokens', 0))} |",
                f"| Cached tokens | {_cell(model.get('cached_tokens', 0))} |",
                f"| Estimated cost | {_cell(model.get('estimated_cost'))} |",
                f"| Finish reason | {_cell(model.get('finish_reason'))} |",
            ]
        )
    if error_message or suggested_fix:
        attention_title = (
            "Why this step was skipped"
            if status == "skipped"
            else "What needs attention"
        )
        lines.extend(
            [
                "",
                f"## {attention_title}",
                "",
                *(
                    [f"- Error type: {error_type or 'Step failure'}"]
                    if status != "skipped"
                    else []
                ),
                f"- Details: {error_message or 'No details were provided.'}",
                f"- Recommended action: {suggested_fix or 'Inspect the linked artifacts and retry.'}",
            ]
        )
    lines.extend(
        ["", "## Inputs", "", *_artifact_lines(input_artifacts, report_path.parent)]
    )
    lines.extend(
        ["", "## Outputs", "", *_artifact_lines(output_artifacts, report_path.parent)]
    )
    _atomic_text(report_path, "\n".join(lines))


def _finished_steps(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [event for event in events if event.get("event_type") == "step_finished"]


def write_run_views(
    state: Mapping[str, Any],
    paths: Mapping[str, str],
    summary: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
) -> None:
    """Refresh the root run report and compact Markdown timeline."""
    run_dir = Path(paths["run_dir"])
    finished = _finished_steps(events)
    timeline_lines = [
        "# Run Timeline",
        "",
        "| # | Step | Attempt | Status | Duration | Model | Tokens | Report |",
        "|---:|---|---:|---|---:|---|---:|---|",
    ]
    for index, event in enumerate(finished, start=1):
        report = event.get("step_report")
        report_link = _relative_link(str(report), run_dir) if report else "—"
        tokens = int(event.get("input_tokens") or 0) + int(
            event.get("output_tokens") or 0
        )
        timeline_lines.append(
            "| {index} | {step} | {attempt} | {status} | {duration} ms | {model} | {tokens} | {report} |".format(
                index=index,
                step=_cell(step_title(str(event.get("step_id") or "unknown"))),
                attempt=_cell(event.get("attempt")),
                status=_cell(event.get("status")),
                duration=_cell(event.get("duration_ms")),
                model=_cell(event.get("model")),
                tokens=tokens,
                report=report_link,
            )
        )
    if not finished:
        timeline_lines.append(
            "| 1 | Workflow initialization | — | running | — | — | 0 | — |"
        )
    _atomic_text(Path(paths["timeline_path"]), "\n".join(timeline_lines))

    status = str(summary.get("status") or state.get("job_status") or "running")
    report_lines = [
        f"# Run Report: {state.get('project_name', 'project')}",
        "",
        "> Start here. This report summarizes what happened, what failed, and what to inspect next.",
        "",
        "## Run overview",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Run ID | {_cell(state.get('run_id'))} |",
        f"| Job ID | {_cell(state.get('job_id'))} |",
        f"| Stack | {_cell(state.get('target_stack', 'both'))} |",
        f"| Status | **{_cell(status)}** |",
        f"| Current phase | {_cell(summary.get('current_phase'))} |",
        f"| Started | {_cell(summary.get('started_at'))} |",
        f"| Finished | {_cell(summary.get('ended_at'))} |",
        "",
        "## Request",
        "",
        str(state.get("raw_request") or state.get("user_prompt") or "_Not recorded._"),
        "",
        "## What needs attention",
        "",
    ]
    action_items = list(summary.get("action_items") or [])
    if action_items:
        for item in action_items:
            report_lines.extend(
                [
                    f"### {step_title(str(item.get('step_id') or 'step'))}",
                    "",
                    f"- Status: {item.get('status', 'failed')}",
                    f"- Problem: {item.get('message') or 'See the step report.'}",
                    f"- Recommended action: {item.get('suggested_fix') or 'Inspect and retry the step.'}",
                    *(
                        [
                            f"- Step report: {_relative_link(str(item['step_report']), run_dir)}"
                        ]
                        if item.get("step_report")
                        else []
                    ),
                    "",
                ]
            )
    else:
        report_lines.extend(
            ["No failed or blocked steps currently need attention.", ""]
        )
    report_lines.extend(
        [
            "## Usage",
            "",
            f"- Step attempts: {summary.get('step_attempts', 0)}",
            f"- Input tokens: {summary.get('input_tokens', 0)}",
            f"- Output tokens: {summary.get('output_tokens', 0)}",
            f"- Reasoning tokens: {summary.get('reasoning_tokens', 0)}",
            f"- Estimated cost: {summary.get('estimated_cost') if summary.get('estimated_cost') is not None else 'not configured'}",
            "",
            "## Where to look",
            "",
            f"- [Readable step timeline]({_relative_path(paths['timeline_path'], run_dir)})",
            "- `steps/` contains one readable report per step plus model prompts/responses when applicable.",
            "- `events.jsonl` is the append-only machine timeline used by agents and future queue workers.",
            "- `_machine/` contains derived indexes and hashes; it is not the starting point for debugging.",
        ]
    )
    _atomic_text(Path(paths["run_report_path"]), "\n".join(report_lines))
