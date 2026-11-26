"""
Final reporting agent.

This module assembles a concise delivery summary from the completed workflow,
including build, verification, and repair history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint


def build_delivery_summary(state: Dict[str, Any]) -> str:
    """Build a concise end-of-job delivery summary."""
    verification_results = list(state.get("verification_results") or [])
    repair_history = list(state.get("repair_history") or [])
    completed_specs = list(state.get("completed_specs") or [])
    failed_specs = list(state.get("failed_specs") or [])
    execution_plan = state.get("execution_plan") or {}
    artifacts = state.get("artifacts") or {}
    python_output = state.get("python_output") or {}
    nodejs_output = state.get("nodejs_output") or {}

    last_verification = verification_results[-1] if verification_results else {}
    last_repair = repair_history[-1] if repair_history else {}

    lines = [
        "# Delivery Summary",
        "",
        f"**Job ID**: {state.get('job_id', '')}",
        f"**Project**: {state.get('project_name', '')}",
        f"**Current Phase**: {state.get('current_phase', '')}",
        f"**Job Status**: {state.get('job_status', '')}",
        f"**Checkpoint**: {state.get('checkpoint_path', state.get('checkpoint_ref', ''))}",
        "",
        "## Build Outputs",
        f"- Python output: {python_output.get('status', 'n/a')}",
        f"- Node.js output: {nodejs_output.get('status', 'n/a')}",
        "",
        "## Execution",
        f"- Ordered specs: {len(execution_plan.get('ordered_specs', []))}",
        f"- Completed specs: {len(completed_specs)}",
        f"- Failed specs: {len(failed_specs)}",
        "",
        "## Verification",
        f"- Verification runs: {len(verification_results)}",
        f"- Last verification status: {last_verification.get('status', 'n/a')}",
        f"- Last failure category: {last_verification.get('failure_category', 'n/a')}",
        "",
        "## Repair",
        f"- Repair runs: {len(repair_history)}",
        f"- Last repair status: {last_repair.get('status', 'n/a')}",
        "",
        "## Artifacts",
        f"- Requirements: {artifacts.get('requirements_dir', '')}",
        f"- Architecture: {artifacts.get('architecture_dir', '')}",
        f"- Specs: {artifacts.get('specs_dir', '')}",
        f"- Plans: {artifacts.get('plans_dir', '')}",
        f"- Builds: {artifacts.get('builds_dir', '')}",
        f"- Verification: {artifacts.get('verification_dir', '')}",
        f"- Repairs: {artifacts.get('repairs_dir', '')}",
        f"- Reports: {artifacts.get('reports_dir', '')}",
        f"- Checkpoints: {artifacts.get('checkpoints_dir', '')}",
        "",
    ]
    return "\n".join(lines)


def persist_delivery_summary(
    state: Dict[str, Any],
    *,
    summary_name: str | None = None,
) -> Dict[str, str]:
    """Persist the final delivery summary and final checkpoint."""
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    reports_dir = Path(manifest["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary_filename = summary_name or "delivery-summary.md"
    summary_path = reports_dir / summary_filename
    summary_path.write_text(build_delivery_summary(state), encoding="utf-8")
    checkpoint_path = persist_job_checkpoint(state, manifest, suffix="final")
    return {
        "delivery_summary_markdown": str(summary_path),
        "final_checkpoint_path": str(checkpoint_path),
    }
