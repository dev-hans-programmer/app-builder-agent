"""
Runtime helpers for workflow jobs, artifacts, and checkpoints.

These utilities provide the durable foundation for spec-driven execution:
- job metadata
- workspace layout
- checkpoint persistence
- phase/status updates
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict
from uuid import uuid4

WORKSPACE_DIRS = (
    "requirements",
    "architecture",
    "specs",
    "plans",
    "execution",
    "builds",
    "verification",
    "repairs",
    "reports",
    "checkpoints",
)

JOB_PHASES = (
    "intake",
    "requirement_analysis",
    "architecture_planning",
    "spec_decomposition",
    "planning",
    "execution",
    "verification",
    "repair",
    "reporting",
    "completed",
)

JOB_STATUSES = (
    "initialized",
    "running",
    "paused",
    "blocked",
    "failed",
    "completed",
)


class RequirementArtifact(TypedDict, total=False):
    """Structured requirement artifact generated from a prompt or PRD."""

    id: str
    title: str
    source_type: str
    summary: str
    goals: list[str]
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    constraints: list[str]
    assumptions: list[str]
    open_questions: list[str]
    clarification_answers: list[Dict[str, str]]
    out_of_scope: list[str]
    complexity: str
    created_at: str


class ArchitectureArtifact(TypedDict, total=False):
    """Structured architecture artifact generated from normalized requirements."""

    id: str
    title: str
    source_requirement_id: str
    summary: str
    layers: list[str]
    module_map: Dict[str, list[str]]
    service_boundaries: list[str]
    data_model: list[str]
    api_surface: list[str]
    security_strategy: list[str]
    configuration_strategy: list[str]
    observability_strategy: list[str]
    deployment_notes: list[str]
    decisions: list[str]
    risks: list[str]
    primary_entities: list[str]
    rbac_model: list[str]
    lifecycle: list[str]
    verification_strategy: list[str]
    complexity: str
    created_at: str


class SpecArtifact(TypedDict, total=False):
    """Structured implementation spec artifact."""

    id: str
    title: str
    order: int
    level: str
    module_name: str
    folder_name: str
    objective: str
    scope: str
    dependencies: list[str]
    acceptance_criteria: list[str]
    verification_steps: list[str]
    implementation_notes: list[str]
    prompt: str
    tasks: list[Dict[str, Any]]
    artifact_paths: Dict[str, str]
    owner: str
    status: str
    created_at: str


class PlanArtifact(TypedDict, total=False):
    """Structured execution plan artifact."""

    id: str
    title: str
    ordered_specs: list[str]
    dependency_graph: Dict[str, list[str]]
    parallel_groups: list[list[str]]
    checkpoints: list[str]
    retry_policy: Dict[str, Any]
    status: str
    created_at: str


class ArtifactManifest(TypedDict, total=False):
    """Filesystem artifact manifest for the workflow."""

    workspace_root: str
    project_name: str
    requirements_dir: str
    architecture_dir: str
    specs_dir: str
    plans_dir: str
    execution_dir: str
    builds_dir: str
    verification_dir: str
    repairs_dir: str
    reports_dir: str
    checkpoints_dir: str
    runs_dir: str
    run_dir: str
    run_report_path: str
    timeline_path: str
    events_path: str
    machine_dir: str
    run_metadata_path: str
    run_summary_path: str
    artifact_manifest_path: str
    steps_dir: str
    comparison_report_markdown: str
    delivery_summary_markdown: str
    final_checkpoint_path: str


class JobMetadata(TypedDict, total=False):
    """Durable metadata for a workflow job."""

    job_id: str
    run_id: str
    job_status: str
    current_phase: str
    input_type: str
    raw_request: str
    checkpoint_ref: str
    resume_token: str
    created_at: str
    updated_at: str


class CheckpointData(TypedDict, total=False):
    """Serializable checkpoint payload."""

    job_id: str
    run_id: str
    checkpoint_ref: str
    current_phase: str
    job_status: str
    state: Dict[str, Any]
    artifacts: ArtifactManifest
    created_at: str


class WorkspaceWriteResult(TypedDict, total=False):
    """Result metadata for a controlled workspace write."""

    path: str
    created: bool
    overwritten: bool
    bytes_written: int
    changed: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job_metadata(
    *,
    input_type: str,
    raw_request: str,
    current_phase: str = "intake",
    job_status: str = "initialized",
    job_id: Optional[str] = None,
    run_id: Optional[str] = None,
    checkpoint_ref: Optional[str] = None,
    resume_token: Optional[str] = None,
) -> JobMetadata:
    """Create a serializable job metadata record."""
    timestamp = _now_iso()
    job_identifier = job_id or f"job-{uuid4().hex[:12]}"
    run_identifier = run_id or f"run-{job_identifier.removeprefix('job-')}"
    checkpoint_identifier = checkpoint_ref or f"checkpoint-{uuid4().hex[:12]}"
    resume_identifier = resume_token or uuid4().hex

    return JobMetadata(
        job_id=job_identifier,
        run_id=run_identifier,
        job_status=job_status,
        current_phase=current_phase,
        input_type=input_type,
        raw_request=raw_request,
        checkpoint_ref=checkpoint_identifier,
        resume_token=resume_identifier,
        created_at=timestamp,
        updated_at=timestamp,
    )


def create_artifact_manifest(
    base_dir: str | Path = ".",
    *,
    project_name: str | None = None,
    run_id: str | None = None,
) -> ArtifactManifest:
    """Create the standard artifact manifest without touching the filesystem."""
    root = Path(base_dir).resolve()
    if project_name:
        if root.name != "projects":
            root = root / "projects"
        root = root / project_name
    manifest = ArtifactManifest(
        workspace_root=str(root),
        project_name=str(project_name or ""),
        requirements_dir=str(root / "requirements"),
        architecture_dir=str(root / "architecture"),
        specs_dir=str(root / "specs"),
        plans_dir=str(root / "plans"),
        execution_dir=str(root / "execution"),
        builds_dir=str(root / "builds"),
        verification_dir=str(root / "verification"),
        repairs_dir=str(root / "repairs"),
        reports_dir=str(root / "reports"),
        checkpoints_dir=str(root / "checkpoints"),
        runs_dir=str(root / "runs"),
    )
    if run_id:
        run_dir = root / "runs" / run_id
        machine_dir = run_dir / "_machine"
        manifest.update(
            run_dir=str(run_dir),
            run_report_path=str(run_dir / "README.md"),
            timeline_path=str(run_dir / "timeline.md"),
            events_path=str(run_dir / "events.jsonl"),
            machine_dir=str(machine_dir),
            run_metadata_path=str(machine_dir / "metadata.json"),
            run_summary_path=str(machine_dir / "summary.json"),
            artifact_manifest_path=str(machine_dir / "artifacts.json"),
            steps_dir=str(run_dir / "steps"),
        )
    return manifest


def ensure_workspace_layout(
    base_dir: str | Path = ".",
    *,
    project_name: str | None = None,
    run_id: str | None = None,
) -> ArtifactManifest:
    """
    Create the canonical workspace folders used by the spec-driven workflow.

    The function is idempotent and safe to call on every job start.
    """
    manifest = create_artifact_manifest(
        base_dir, project_name=project_name, run_id=run_id
    )
    for key in (
        "requirements_dir",
        "architecture_dir",
        "specs_dir",
        "plans_dir",
        "execution_dir",
        "builds_dir",
        "verification_dir",
        "repairs_dir",
        "reports_dir",
        "checkpoints_dir",
        "runs_dir",
    ):
        Path(manifest[key]).mkdir(parents=True, exist_ok=True)
    if manifest.get("run_dir"):
        Path(manifest["run_dir"]).mkdir(parents=True, exist_ok=True)
        Path(manifest["machine_dir"]).mkdir(parents=True, exist_ok=True)
        Path(manifest["steps_dir"]).mkdir(parents=True, exist_ok=True)
    return manifest


def save_checkpoint(checkpoint_path: str | Path, data: Dict[str, Any]) -> Path:
    """Persist checkpoint data as JSON and return the written path."""
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def persist_job_checkpoint(
    state: Dict[str, Any],
    artifacts: ArtifactManifest,
    *,
    suffix: Optional[str] = None,
) -> Path:
    """Persist the current job state to a checkpoint file."""
    phase = suffix or str(state.get("current_phase", "state"))
    checkpoint_dir = Path(artifacts["checkpoints_dir"])
    checkpoint_path = checkpoint_dir / f"{phase}.json"
    checkpoint_data = build_checkpoint_data(state, artifacts)
    save_checkpoint(checkpoint_path, checkpoint_data)
    return checkpoint_path


def load_checkpoint(checkpoint_path: str | Path) -> Dict[str, Any]:
    """Load a checkpoint JSON file."""
    path = Path(checkpoint_path)
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_checkpoint(checkpoints_dir: str | Path) -> Optional[Path]:
    """Return the most recently modified checkpoint file, if any."""
    directory = Path(checkpoints_dir)
    if not directory.exists():
        return None
    checkpoint_files = sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    return checkpoint_files[-1] if checkpoint_files else None


def restore_state_from_checkpoint(
    checkpoint: Dict[str, Any],
    *,
    checkpoint_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Restore a workflow state from serialized checkpoint data."""
    restored = dict(checkpoint.get("state", {}))
    restored.setdefault("job_id", checkpoint.get("job_id", ""))
    restored.setdefault(
        "run_id",
        checkpoint.get("run_id")
        or f"run-{str(restored.get('job_id', '')).removeprefix('job-')}",
    )
    restored.setdefault("current_phase", checkpoint.get("current_phase", "intake"))
    restored.setdefault("job_status", checkpoint.get("job_status", "initialized"))
    restored["artifacts"] = checkpoint.get("artifacts", restored.get("artifacts", {}))
    restored["checkpoint_ref"] = checkpoint.get(
        "checkpoint_ref", restored.get("checkpoint_ref", "")
    )
    if checkpoint_path is not None:
        restored["checkpoint_path"] = str(checkpoint_path)
    return restored


def advance_job_phase(
    state: Dict[str, Any], phase: str, *, status: Optional[str] = None
) -> Dict[str, Any]:
    """Return a copy of state with an updated phase/status and timestamp."""
    if phase not in JOB_PHASES:
        raise ValueError(f"Unknown workflow phase: {phase}")

    updated = dict(state)
    updated["current_phase"] = phase
    if status is not None:
        if status not in JOB_STATUSES:
            raise ValueError(f"Unknown job status: {status}")
        updated["job_status"] = status
    updated["updated_at"] = _now_iso()
    return updated


def mark_job_status(state: Dict[str, Any], status: str) -> Dict[str, Any]:
    """Return a copy of state with an updated job status."""
    if status not in JOB_STATUSES:
        raise ValueError(f"Unknown job status: {status}")
    updated = dict(state)
    updated["job_status"] = status
    updated["updated_at"] = _now_iso()
    return updated


def build_checkpoint_data(
    state: Dict[str, Any],
    artifacts: ArtifactManifest,
) -> CheckpointData:
    """Build a serializable checkpoint payload from the current state."""
    return CheckpointData(
        job_id=str(state.get("job_id", "")),
        run_id=str(state.get("run_id", "")),
        checkpoint_ref=str(state.get("checkpoint_ref", "")),
        current_phase=str(state.get("current_phase", "")),
        job_status=str(state.get("job_status", "")),
        state=dict(state),
        artifacts=artifacts,
        created_at=_now_iso(),
    )
