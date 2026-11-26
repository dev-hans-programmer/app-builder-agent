"""
Verification and repair agent.

This module verifies executor outputs for the current spec, classifies
failures, persists verification results, and applies targeted repairs before
re-verifying.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.agents.executor import (
    _find_spec_node,
    _safe_resolve_path,
    write_json_safely,
    write_text_safely,
)
from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


def _execution_paths(
    manifest: Dict[str, str],
    project_name: str,
    spec_id: str,
    job_id: str,
) -> tuple[Path, Path, Path, Path, Path]:
    execution_dir = Path(manifest["execution_dir"]) / spec_id
    plans_dir = Path(manifest["plans_dir"])
    checkpoints_dir = Path(manifest["checkpoints_dir"])
    return (
        execution_dir / "summary.json",
        execution_dir / "summary.md",
        plans_dir / "execution-trace.json",
        plans_dir / "execution-trace.md",
        checkpoints_dir / f"{spec_id}.json",
    )


def _verification_paths(manifest: Dict[str, str], job_id: str) -> tuple[Path]:
    verification_dir = Path(manifest["verification_dir"])
    return (verification_dir / "verification.md",)


def _repair_paths(manifest: Dict[str, str], job_id: str) -> tuple[Path]:
    repairs_dir = Path(manifest["repairs_dir"])
    return (repairs_dir / "repair.md",)


def _build_check(name: str, passed: bool, details: str) -> Dict[str, Any]:
    return {"name": name, "passed": passed, "details": details}


def classify_failure(verification_result: Dict[str, Any]) -> str:
    """Classify a verification failure for routing and recovery."""
    if verification_result.get("status") == "passed":
        return "none"

    missing = set(verification_result.get("missing_artifacts", []))
    if not verification_result.get("spec_id"):
        return "blocked-by-missing-input"
    if missing & {"summary.json", "summary.md"}:
        return "local"
    if missing & {"trace.json", "trace.md"}:
        return "environment-related"
    if missing & {"checkpoint.json"}:
        return "cascading"
    return "local"


def build_verification_result(state: BuilderState) -> Dict[str, Any]:
    """Verify the current spec artifacts."""
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    spec_tree = state.get("spec_tree") or {}
    current_spec_id = state.get("current_spec_id") or ""
    project_name = state["project_name"]
    spec_node = _find_spec_node(spec_tree, current_spec_id) if current_spec_id else None

    (
        summary_json_path,
        summary_md_path,
        trace_json_path,
        trace_md_path,
        checkpoint_path,
    ) = _execution_paths(
        manifest,
        project_name,
        current_spec_id,
        state["job_id"],
    )
    (verification_md_path,) = _verification_paths(manifest, state["job_id"])

    checks: list[Dict[str, Any]] = []
    missing_artifacts: list[str] = []

    summary_json_exists = _safe_resolve_path(
        manifest["workspace_root"], summary_json_path
    ).exists()
    summary_md_exists = _safe_resolve_path(
        manifest["workspace_root"], summary_md_path
    ).exists()
    trace_json_exists = _safe_resolve_path(
        manifest["workspace_root"], trace_json_path
    ).exists()
    trace_md_exists = _safe_resolve_path(
        manifest["workspace_root"], trace_md_path
    ).exists()
    checkpoint_exists = checkpoint_path.exists()

    checks.append(
        _build_check("summary.json exists", summary_json_exists, str(summary_json_path))
    )
    checks.append(
        _build_check("summary.md exists", summary_md_exists, str(summary_md_path))
    )
    checks.append(
        _build_check("trace.json exists", trace_json_exists, str(trace_json_path))
    )
    checks.append(_build_check("trace.md exists", trace_md_exists, str(trace_md_path)))
    checks.append(
        _build_check("checkpoint exists", checkpoint_exists, str(checkpoint_path))
    )

    if not summary_json_exists:
        missing_artifacts.append("summary.json")
    if not summary_md_exists:
        missing_artifacts.append("summary.md")
    if not trace_json_exists:
        missing_artifacts.append("trace.json")
    if not trace_md_exists:
        missing_artifacts.append("trace.md")
    if not checkpoint_exists:
        missing_artifacts.append("checkpoint.json")

    if spec_node and summary_md_exists:
        summary_text = _safe_resolve_path(
            manifest["workspace_root"], summary_md_path
        ).read_text(encoding="utf-8")
        checks.append(
            _build_check(
                "summary references spec title",
                spec_node.get("title", "") in summary_text,
                spec_node.get("title", ""),
            )
        )
    else:
        checks.append(
            _build_check(
                "summary references spec title",
                False,
                "summary.md missing or spec missing",
            )
        )

    passed = all(check["passed"] for check in checks)
    failure_category = (
        "none"
        if passed
        else classify_failure(
            {
                "status": "failed",
                "spec_id": current_spec_id,
                "missing_artifacts": missing_artifacts,
            }
        )
    )

    return {
        "spec_id": current_spec_id,
        "passed": passed,
        "status": "passed" if passed else "failed",
        "failure_category": failure_category,
        "checks": checks,
        "missing_artifacts": missing_artifacts,
        "verification_artifact_paths": {
            "verification_markdown": str(verification_md_path),
        },
    }


def persist_verification_result(
    verification_result: Dict[str, Any],
    manifest: Dict[str, str],
    job_id: str,
) -> Dict[str, str]:
    """Persist verification result as a single markdown file."""
    (verification_md_path,) = _verification_paths(manifest, job_id)
    verification_md_path.parent.mkdir(parents=True, exist_ok=True)
    verification_md_path.write_text(
        "\n".join(
            [
                "# Verification Result",
                "",
                f"**Spec**: {verification_result.get('spec_id', '')}",
                f"**Status**: {verification_result.get('status', '')}",
                f"**Failure Category**: {verification_result.get('failure_category', 'none')}",
                "",
                "## Checks",
                *[
                    f"- [{'x' if check['passed'] else ' '}] {check['name']}: {check['details']}"
                    for check in verification_result.get("checks", [])
                ],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "verification_markdown": str(verification_md_path),
        "verification_json": str(verification_md_path),
    }


def persist_repair_result(
    repair_result: Dict[str, Any],
    manifest: Dict[str, str],
    job_id: str,
) -> Dict[str, str]:
    """Persist repair result as a single markdown file."""
    (repair_md_path,) = _repair_paths(manifest, job_id)
    repair_md_path.parent.mkdir(parents=True, exist_ok=True)
    repair_md_path.write_text(
        "\n".join(
            [
                "# Repair Result",
                "",
                f"**Job**: {job_id}",
                f"**Status**: {repair_result.get('status', '')}",
                f"**Repaired Files**: {len(repair_result.get('repaired_files', []))}",
                "",
                "## Repaired Files",
                *[f"- {path}" for path in repair_result.get("repaired_files", [])],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "repair_markdown": str(repair_md_path),
        "repair_json": str(repair_md_path),
    }


def _repair_spec_artifacts(
    state: BuilderState, verification_result: Dict[str, Any]
) -> list[str]:
    """Repair missing execution artifacts using the current spec."""
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    spec_tree = state.get("spec_tree") or {}
    current_spec_id = (
        state.get("current_spec_id") or verification_result.get("spec_id") or ""
    )
    spec_node = _find_spec_node(spec_tree, current_spec_id) if current_spec_id else None
    project_name = state["project_name"]
    repaired_files: list[str] = []

    if not spec_node:
        return repaired_files

    (
        summary_json_path,
        summary_md_path,
        trace_json_path,
        trace_md_path,
        checkpoint_path,
    ) = _execution_paths(
        manifest,
        project_name,
        current_spec_id,
        state["job_id"],
    )
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
            "",
            "## Files Written",
            f"- {summary_json_path}",
            f"- {summary_md_path}",
            f"- {trace_json_path}",
            f"- {trace_md_path}",
            "",
        ]
    )

    if "summary.json" in verification_result.get("missing_artifacts", []):
        result = write_json_safely(
            manifest["workspace_root"], summary_json_path, summary_payload
        )
        if result["changed"]:
            repaired_files.append(result["path"])
    if "summary.md" in verification_result.get("missing_artifacts", []):
        result = write_text_safely(
            manifest["workspace_root"], summary_md_path, summary_md
        )
        if result["changed"]:
            repaired_files.append(result["path"])
    if "trace.json" in verification_result.get("missing_artifacts", []):
        result = write_json_safely(
            manifest["workspace_root"],
            trace_json_path,
            {
                "job_id": state["job_id"],
                "current_spec_id": current_spec_id,
                "trace": state.get("execution_trace", []),
            },
        )
        if result["changed"]:
            repaired_files.append(result["path"])
    if "trace.md" in verification_result.get("missing_artifacts", []):
        result = write_text_safely(manifest["workspace_root"], trace_md_path, trace_md)
        if result["changed"]:
            repaired_files.append(result["path"])
    if "checkpoint.json" in verification_result.get("missing_artifacts", []):
        result = write_json_safely(
            manifest["workspace_root"],
            checkpoint_path,
            {
                "job_id": state["job_id"],
                "current_spec_id": current_spec_id,
                "trace": state.get("execution_trace", []),
            },
        )
        if result["changed"]:
            repaired_files.append(result["path"])

    return repaired_files


def verify_execution(state: BuilderState) -> Dict[str, Any]:
    """Run verification and persist the result."""
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    verification_result = build_verification_result(state)
    verification_paths = persist_verification_result(
        verification_result, manifest, state["job_id"]
    )
    verification_entry = {
        **verification_result,
        "verification_paths": verification_paths,
    }
    verification_results = list(state.get("verification_results", [])) + [
        verification_entry
    ]

    updates = {
        "verification_results": verification_results,
        "job_status": "running" if verification_result["passed"] else "blocked",
        "current_phase": "verification",
        "artifacts": manifest,
        "failed_specs": list(state.get("failed_specs", []))
        + (
            []
            if verification_result["passed"]
            else [verification_result.get("spec_id", "")]
        ),
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, manifest, suffix="verification")
    )
    return updates


def repair_execution(state: BuilderState) -> Dict[str, Any]:
    """Repair the latest verification failure and re-run verification."""
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    verification_history = list(state.get("verification_results", []))
    latest = (
        verification_history[-1]
        if verification_history
        else build_verification_result(state)
    )

    if latest.get("passed"):
        repair_result = {
            "status": "skipped",
            "spec_id": latest.get("spec_id", ""),
            "repaired_files": [],
            "verification_result": latest,
        }
        persist_repair_result(repair_result, manifest, state["job_id"])
        updates = {
            "job_status": "running",
            "current_phase": "repair",
            "artifacts": manifest,
            "repair_history": list(state.get("repair_history", [])) + [repair_result],
        }
        updates["checkpoint_path"] = str(
            persist_job_checkpoint({**state, **updates}, manifest, suffix="repair")
        )
        return updates

    repaired_files = _repair_spec_artifacts(state, latest)
    repaired_verification = build_verification_result(state)
    verification_paths = persist_verification_result(
        repaired_verification, manifest, state["job_id"]
    )
    repair_result = {
        "status": "repaired" if repaired_verification.get("passed") else "blocked",
        "spec_id": repaired_verification.get("spec_id", ""),
        "failure_category": latest.get("failure_category", "local"),
        "repaired_files": repaired_files,
        "verification_result": repaired_verification,
        "verification_paths": verification_paths,
    }
    persist_repair_result(repair_result, manifest, state["job_id"])

    repaired_history = list(state.get("repair_history", [])) + [repair_result]
    failed_specs = list(state.get("failed_specs", []))
    if (
        not repaired_verification.get("passed")
        and repaired_verification.get("spec_id") not in failed_specs
    ):
        failed_specs.append(repaired_verification.get("spec_id", ""))

    updates = {
        "current_phase": "repair",
        "job_status": "running" if repaired_verification.get("passed") else "blocked",
        "verification_results": verification_history + [repaired_verification],
        "repair_history": repaired_history,
        "failed_specs": failed_specs,
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, manifest, suffix="repair")
    )
    return updates
