"""Bounded, model-assisted repair of files implicated by quality failures."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.agents.model_request import (
    chat_completion_options,
    completion_finish_reason,
    require_visible_completion,
)
from src.agents.python_builder import (
    apply_file_patches,
    extract_response_text,
    parse_code_blocks,
    parse_generation_response,
    read_project_files,
)
from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState
from src.observability import record_step_artifact
from src.observability.model_usage import model_observability
from src.policy import policy_text_for_task


REPAIR_PROMPT_VERSION = "1.0"


def _repair_prompt(
    state: BuilderState,
    stack: str,
    failures: list[dict[str, Any]],
    current_files: dict[str, str],
) -> str:
    framework = "Python/FastAPI" if stack == "python" else "Node.js/Express"
    policy = state.get("backend_policy") or {}
    policy_text = (
        policy_text_for_task(policy, "repair")
        if stack == "python" and policy.get("enabled")
        else "No stack-specific production policy applies."
    )
    output_contract = (
        """Return JSON only, without Markdown, using this exact envelope:
{
  "task_id": "repair",
  "acceptance_criteria_ids": [],
  "policy_rule_ids": [],
  "files": [{"path": "relative/path", "content": "complete file contents"}]
}"""
        if stack == "python" and policy.get("enabled")
        else """Return complete contents for every changed or new file using exactly:
```filename: path/to/file
[complete file contents]
```"""
    )
    return f"""You are repairing a generated {framework} application.

Change only what is necessary to fix the reported failures. Approved acceptance criteria and
architecture contracts are binding. Preserve unrelated behavior.
{output_contract}
Do not return diffs, explanations, deleted-file instructions, or placeholder code.

Project: {state["project_name"]}
Original request: {state["user_prompt"]}

Binding production policy:
{policy_text}

Approved requirements:
{json.dumps(state.get("requirements") or {}, indent=2, sort_keys=True)}

Architecture contracts:
{json.dumps(state.get("architecture_plan") or {}, indent=2, sort_keys=True)}

Failed checks:
{json.dumps(failures, indent=2, sort_keys=True)}

Current files:
{json.dumps(current_files, indent=2, sort_keys=True)}
"""


def _failed_stack_checks(state: BuilderState) -> list[tuple[str, list[dict[str, Any]]]]:
    failed: list[tuple[str, list[dict[str, Any]]]] = []
    for result in (state.get("quality_results") or {}).get("stacks", []):
        checks = [
            check
            for check in result.get("checks", [])
            if check.get("status") == "failed"
        ]
        if not result.get("passed"):
            if not checks:
                checks = [
                    {
                        "category": "generation",
                        "stderr": result.get("error", "Generation failed."),
                    }
                ]
            failed.append((result["stack"], checks))
    return failed


def _render_repair_report(attempt: int, records: list[dict[str, Any]]) -> str:
    lines = [f"# Targeted Repair Attempt {attempt}", ""]
    for record in records:
        lines.extend(
            [
                f"## {record['stack'].title()}",
                "",
                f"- Status: {record['status']}",
                f"- Failed checks: {', '.join(record.get('failed_checks', [])) or 'none'}",
                f"- Patched files: {', '.join(patch['path'] for patch in record.get('patches', [])) or 'none'}",
                f"- Error: {record.get('error', 'none')}",
                "",
            ]
        )
    return "\n".join(lines)


def repair_failed_checks(state: BuilderState) -> dict[str, Any]:
    """Apply one targeted repair attempt, then let the graph rerun quality gates."""
    attempt = int(state.get("repair_attempt", 0)) + 1
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".", project_name=state.get("project_name")
    )
    failed = _failed_stack_checks(state)
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    options = chat_completion_options(model)
    client = OpenAI(api_key=api_key) if api_key else None
    updates: dict[str, Any] = {}
    records: list[dict[str, Any]] = []

    for stack, checks in failed:
        output_key = "python_output" if stack == "python" else "nodejs_output"
        output = dict(state.get(output_key) or {})
        output_dir = Path(
            output.get("output_dir") or Path(manifest["builds_dir"]) / stack
        )
        prompt = _repair_prompt(state, stack, checks, read_project_files(output_dir))
        artifact_prefix = f"repair-{attempt:02d}-{stack}"
        record_step_artifact(f"{artifact_prefix}-prompt.txt", prompt)
        if client is None:
            records.append(
                {
                    "stack": stack,
                    "status": "skipped",
                    "failed_checks": [
                        check.get("category", "unknown") for check in checks
                    ],
                    "patches": [],
                    "error": "OPENAI_API_KEY is not available.",
                }
            )
            continue
        try:
            started = time.perf_counter()
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **options,
            )
            content = extract_response_text(response)
            usage = model_observability(
                model=model,
                prompt=prompt,
                prompt_version=REPAIR_PROMPT_VERSION,
                response=response,
            )
            usage.update(options)
            record_step_artifact(
                f"{artifact_prefix}-response.json",
                {
                    "id": getattr(response, "id", None),
                    "model": getattr(response, "model", model),
                    "content": content,
                    "finish_reason": completion_finish_reason(response),
                    "usage": usage,
                },
            )
            require_visible_completion(content, response, options)
            files = (
                parse_generation_response(content)[0]
                if stack == "python"
                and (state.get("backend_policy") or {}).get("enabled")
                else parse_code_blocks(content)
            )
            if not files:
                raise ValueError("Repair response did not contain any files.")
            patches = apply_file_patches(output_dir, files)
            previous_patches = list(output.get("patches") or [])
            output.update(
                {
                    "status": "success",
                    "output_dir": str(output_dir),
                    "patches": [*previous_patches, *patches],
                    "files_created": sorted(
                        set([*output.get("files_created", []), *files])
                    ),
                    "artifact_paths": sorted(
                        set(
                            [
                                *output.get("artifact_paths", []),
                                *[str(output_dir / path) for path in files],
                            ]
                        )
                    ),
                }
            )
            output["file_count"] = len(output["files_created"])
            updates[output_key] = output
            records.append(
                {
                    "stack": stack,
                    "status": "patched",
                    "failed_checks": [
                        check.get("category", "unknown") for check in checks
                    ],
                    "patches": patches,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "observability": usage,
                }
            )
        except Exception as exc:  # model and parsing failures are retry evidence
            records.append(
                {
                    "stack": stack,
                    "status": "failed",
                    "failed_checks": [
                        check.get("category", "unknown") for check in checks
                    ],
                    "patches": [],
                    "error": str(exc),
                }
            )

    repairs_dir = Path(manifest["repairs_dir"])
    repairs_dir.mkdir(parents=True, exist_ok=True)
    report_path = repairs_dir / f"attempt-{attempt}.md"
    report_path.write_text(_render_repair_report(attempt, records), encoding="utf-8")
    manifest["latest_repair_report_markdown"] = str(report_path)
    record_statuses = {item["status"] for item in records}
    repair_status = (
        "patched"
        if record_statuses == {"patched"}
        else "partial"
        if "patched" in record_statuses
        else "failed"
    )
    repair_record = {
        "attempt": attempt,
        "status": repair_status,
        "records": records,
        "artifact_path": str(report_path),
    }
    updates.update(
        {
            "repair_attempt": attempt,
            "repair_history": [*(state.get("repair_history") or []), repair_record],
            "current_phase": "repair",
            "job_status": "running",
            "artifacts": manifest,
        }
    )
    updates["checkpoint_path"] = str(
        persist_job_checkpoint(
            {**state, **updates}, manifest, suffix=f"repair_{attempt}"
        )
    )
    return updates
