"""
Execution engine agent.

This module executes a single spec at a time using controlled workspace writes
and emits traceable execution artifacts plus checkpoint data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from src.graph.runtime import (
    WorkspaceWriteResult,
    build_checkpoint_data,
    ensure_workspace_layout,
    save_checkpoint,
)
from src.graph.state import BuilderState


def _safe_resolve_path(root: str | Path, relative_path: str | Path) -> Path:
    """Resolve a workspace path and reject traversal outside the root."""
    root_path = Path(root).resolve()
    candidate = (root_path / relative_path).resolve()
    if root_path not in candidate.parents and candidate != root_path:
        raise ValueError("Path escapes the workspace root")
    return candidate


def write_text_safely(
    root: str | Path,
    relative_path: str | Path,
    content: str,
) -> WorkspaceWriteResult:
    """Write text to a workspace path without escaping the workspace root."""
    target = _safe_resolve_path(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    existed = target.exists()
    previous = target.read_text(encoding="utf-8") if existed else None
    changed = previous != content

    if changed:
        target.write_text(content, encoding="utf-8")

    return WorkspaceWriteResult(
        path=str(target),
        created=not existed,
        overwritten=existed and changed,
        bytes_written=len(content.encode("utf-8")) if changed else 0,
        changed=changed,
    )


def write_json_safely(
    root: str | Path,
    relative_path: str | Path,
    payload: Dict[str, Any],
) -> WorkspaceWriteResult:
    """Write JSON to a workspace path without escaping the workspace root."""
    content = json.dumps(payload, indent=2, sort_keys=True)
    return write_text_safely(root, relative_path, content)


def _find_spec_node(spec_tree: Dict[str, Any], spec_id: str) -> Dict[str, Any] | None:
    """Find a spec node by id anywhere in the spec tree."""
    for epic in spec_tree.get("epics", []):
        if epic.get("id") == spec_id:
            return epic
        for feature in epic.get("features", []):
            if feature.get("id") == spec_id:
                return feature
            for component in feature.get("components", []):
                if component.get("id") == spec_id:
                    return component
                for task in component.get("tasks", []):
                    if task.get("id") == spec_id:
                        return task
    return None


def _build_trace_entry(
    spec_node: Dict[str, Any],
    changed_files: list[str],
    checkpoint_path: str,
) -> Dict[str, Any]:
    return {
        "spec_id": spec_node.get("id", ""),
        "title": spec_node.get("title", ""),
        "level": spec_node.get("level", ""),
        "objective": spec_node.get("objective", ""),
        "status": "completed",
        "changed_files": changed_files,
        "checkpoint_path": checkpoint_path,
    }


def execute_spec(state: BuilderState) -> Dict[str, Any]:
    """
    Execute a single spec with controlled workspace writes.
    """
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    execution_plan = state.get("execution_plan") or {}
    spec_tree = state.get("spec_tree") or {}
    ordered_specs = list(execution_plan.get("ordered_specs", []))
    if not ordered_specs:
        return {
            "job_status": "failed",
            "current_phase": "execution",
            "errors": state.get("errors", []) + ["Execution plan is empty"],
        }

    current_spec_id = state.get("current_spec_id") or ordered_specs[0]
    spec_node = _find_spec_node(spec_tree, current_spec_id)
    if not spec_node:
        return {
            "job_status": "failed",
            "current_phase": "execution",
            "errors": state.get("errors", []) + [f"Spec {current_spec_id} not found in spec tree"],
        }

    workspace_root = manifest["workspace_root"]
    execution_dir = Path(manifest["execution_dir"])
    trace_dir = Path(manifest["plans_dir"])
    spec_slug = current_spec_id.replace("/", "-")

    summary_payload = {
        "spec_id": current_spec_id,
        "title": spec_node.get("title", ""),
        "level": spec_node.get("level", ""),
        "objective": spec_node.get("objective", ""),
        "acceptance_criteria": spec_node.get("acceptance_criteria", []),
        "verification_steps": spec_node.get("verification_steps", []),
        "dependencies": spec_node.get("dependencies", []),
    }

    summary_md = "\n".join(
        [
            f"# Execution Summary for {current_spec_id}",
            "",
            f"**Title**: {spec_node.get('title', '')}",
            f"**Level**: {spec_node.get('level', '')}",
            f"**Objective**: {spec_node.get('objective', '')}",
            "",
            "## Acceptance Criteria",
            *[f"- {item}" for item in spec_node.get("acceptance_criteria", [])],
            "",
            "## Verification Steps",
            *[f"- {item}" for item in spec_node.get("verification_steps", [])],
            "",
        ]
    )

    trace_md = "\n".join(
        [
            "# Execution Trace",
            "",
            f"**Job**: {state['job_id']}",
            f"**Current Spec**: {current_spec_id}",
            f"**Phase**: execution",
            "",
            "## Files Written",
            f"- {execution_dir / spec_slug / 'summary.json'}",
            f"- {execution_dir / spec_slug / 'summary.md'}",
            f"- {trace_dir / 'execution-trace.json'}",
            f"- {trace_dir / 'execution-trace.md'}",
            "",
        ]
    )

    changed_files: list[str] = []
    summary_json_result = write_json_safely(
        workspace_root,
        execution_dir / spec_slug / "summary.json",
        summary_payload,
    )
    if summary_json_result["changed"]:
        changed_files.append(summary_json_result["path"])

    summary_md_result = write_text_safely(
        workspace_root,
        execution_dir / spec_slug / "summary.md",
        summary_md,
    )
    if summary_md_result["changed"]:
        changed_files.append(summary_md_result["path"])

    trace_json_path = Path(trace_dir) / "execution-trace.json"
    trace_md_path = Path(trace_dir) / "execution-trace.md"

    trace_entry = _build_trace_entry(spec_node, changed_files, str(_safe_resolve_path(workspace_root, execution_dir / spec_slug / "summary.json")))
    execution_trace = list(state.get("execution_trace", [])) + [trace_entry]

    trace_json_result = write_json_safely(
        workspace_root,
        trace_json_path,
        {
            "job_id": state["job_id"],
            "current_spec_id": current_spec_id,
            "trace": execution_trace,
        },
    )
    if trace_json_result["changed"]:
        changed_files.append(trace_json_result["path"])

    trace_md_result = write_text_safely(workspace_root, trace_md_path, trace_md)
    if trace_md_result["changed"]:
        changed_files.append(trace_md_result["path"])

    checkpoint_path = _safe_resolve_path(
        workspace_root,
        Path("checkpoints") / f"{current_spec_id}.json",
    )
    checkpoint_data = build_checkpoint_data(
        {
            **state,
            "current_phase": "execution",
            "job_status": "running",
            "current_spec_id": current_spec_id,
            "execution_trace": execution_trace,
        },
        manifest,
    )
    saved_checkpoint = save_checkpoint(checkpoint_path, checkpoint_data)

    completed_specs = list(state.get("completed_specs", []))
    if current_spec_id not in completed_specs:
        completed_specs.append(current_spec_id)

    return {
        "current_phase": "execution",
        "job_status": "running",
        "current_spec_id": current_spec_id,
        "completed_specs": completed_specs,
        "execution_trace": execution_trace,
        "artifacts": manifest,
        "checkpoint_path": str(saved_checkpoint),
    }
