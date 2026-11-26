"""Append-only, run-scoped observability for workflow nodes and artifacts."""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from src.observability.readable import (
    render_model_artifact,
    step_slug,
    write_run_views,
    write_step_finished,
    write_step_started,
)

EVENT_SCHEMA_VERSION = "1.0"
_PROCESS_LOCK = threading.RLock()
_ACTIVE_STEP: contextvars.ContextVar[ActiveStep | None] = contextvars.ContextVar(
    "active_observability_step",
    default=None,
)
_SECRET_KEY = re.compile(
    r"(api[_-]?key|authorization|password|secret|(^|_)(access_token|refresh_token|resume_token|auth_token|token)$)",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret)\s*[:=]\s*([^\s,;]+)"
)
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")


@dataclass
class ActiveStep:
    """Runtime context for one node attempt."""

    run_id: str
    step_id: str
    parent_step_id: str | None
    attempt: int
    span_id: str
    report_path: Path
    artifact_stem: str
    started_at: str
    started_monotonic: float
    input_artifacts: list[str]
    state: dict[str, Any]
    context_token: contextvars.Token[ActiveStep | None] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "dict") and callable(value.dict):
        return _json_safe(value.dict())
    return repr(value)


def _redact_text(value: str) -> str:
    value = _OPENAI_KEY.sub("[REDACTED_API_KEY]", value)
    return _SECRET_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def redact(value: Any, *, key: str = "") -> Any:
    """Convert values to JSON-safe structures while removing likely secrets."""
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    safe = _json_safe(value)
    return _redact_text(safe) if isinstance(safe, str) else safe


def sha256_file(path: str | Path) -> str:
    """Hash a file without loading it entirely into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(redact(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


@contextmanager
def _event_file_lock(run_dir: Path) -> Iterator[None]:
    """Serialize event and manifest writes across threads and local workers."""
    lock_path = run_dir / "_machine" / "events.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESS_LOCK, lock_path.open("a+", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def _run_id(state: Mapping[str, Any]) -> str:
    existing = str(state.get("run_id") or "").strip()
    if existing:
        return existing
    job_id = str(state.get("job_id") or uuid4().hex[:12])
    suffix = job_id.removeprefix("job-")
    return f"run-{suffix}"


def ensure_run_layout(state: dict[str, Any]) -> dict[str, str]:
    """Ensure the canonical run directory and expose it through artifacts."""
    run_id = _run_id(state)
    state["run_id"] = run_id
    artifacts = dict(state.get("artifacts") or {})
    workspace_root = Path(
        artifacts.get("workspace_root")
        or Path.cwd()
        / "projects"
        / str(state.get("project_name") or "untitled-project")
    ).resolve()
    run_dir = workspace_root / "runs" / run_id
    machine_dir = run_dir / "_machine"
    paths = {
        "runs_dir": str(workspace_root / "runs"),
        "run_dir": str(run_dir),
        "run_report_path": str(run_dir / "README.md"),
        "timeline_path": str(run_dir / "timeline.md"),
        "events_path": str(run_dir / "events.jsonl"),
        "machine_dir": str(machine_dir),
        "run_metadata_path": str(machine_dir / "metadata.json"),
        "run_summary_path": str(machine_dir / "summary.json"),
        "artifact_manifest_path": str(machine_dir / "artifacts.json"),
        "steps_dir": str(run_dir / "steps"),
    }
    artifacts.update(paths)
    artifacts.setdefault("workspace_root", str(workspace_root))
    state["artifacts"] = artifacts

    run_dir.mkdir(parents=True, exist_ok=True)
    machine_dir.mkdir(parents=True, exist_ok=True)
    Path(paths["steps_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["events_path"]).touch(exist_ok=True)
    if not Path(paths["artifact_manifest_path"]).exists():
        _atomic_json(
            Path(paths["artifact_manifest_path"]),
            {"schema_version": EVENT_SCHEMA_VERSION, "run_id": run_id, "artifacts": []},
        )
    return paths


def _git_metadata(workspace_root: str) -> dict[str, Any]:
    def run_git(*arguments: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=workspace_root,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "git_sha": run_git("rev-parse", "HEAD"),
        "git_branch": run_git("branch", "--show-current"),
        "git_dirty": bool(run_git("status", "--porcelain")),
    }


def _read_events(events_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not events_path.exists():
        return events
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _last_sequence(events_path: Path) -> int:
    """Read only the tail of the event stream to recover its sequence."""
    if not events_path.exists() or events_path.stat().st_size == 0:
        return 0
    with events_path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""
        while position > 0:
            chunk_size = min(8192, position)
            position -= chunk_size
            handle.seek(position)
            buffer = handle.read(chunk_size) + buffer
            lines = [line for line in buffer.splitlines() if line.strip()]
            if position == 0 or len(lines) > 1:
                for line in reversed(lines):
                    try:
                        return int(json.loads(line).get("sequence", 0))
                    except (
                        json.JSONDecodeError,
                        AttributeError,
                        TypeError,
                        ValueError,
                    ):
                        continue
        return 0


def _update_summary(
    state: Mapping[str, Any],
    paths: Mapping[str, str],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """Incrementally update the compact run summary in constant time."""
    summary_path = Path(paths["run_summary_path"])
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary = {}

    event_type = event.get("event_type")
    step_finished = event_type == "step_finished"
    failed_steps = list(summary.get("failed_steps", []))
    action_items = list(summary.get("action_items", []))
    if step_finished and event.get("status") in {"failed", "blocked"}:
        failed_steps.append(
            {
                "step_id": event.get("step_id"),
                "attempt": event.get("attempt"),
                "status": event.get("status"),
                "error_type": event.get("error_type"),
                "error_message": event.get("error_message"),
                "suggested_fix": event.get("suggested_fix"),
                "step_report": event.get("step_report"),
            }
        )
    if (
        step_finished
        and event.get("status") in {"failed", "blocked", "skipped"}
        and event.get("suggested_fix")
    ):
        action_items.append(
            {
                "step_id": event.get("step_id"),
                "attempt": event.get("attempt"),
                "status": event.get("status"),
                "message": event.get("error_message"),
                "suggested_fix": event.get("suggested_fix"),
                "step_report": event.get("step_report"),
            }
        )

    status = state.get("job_status", summary.get("status", "initialized"))
    if event_type == "run_started":
        status = "running"
    elif event_type == "run_finished":
        status = event.get("status") or status
    elif step_finished and event.get("status") == "failed" and event.get("stack_trace"):
        status = "failed"

    usage_detail = bool(event.get("usage_detail"))
    event_cost = None if usage_detail else event.get("estimated_cost")
    cost_estimated = bool(summary.get("cost_estimated")) or isinstance(
        event_cost, (int, float)
    )
    estimated_cost = (
        round(
            float(summary.get("estimated_cost") or 0) + float(event_cost or 0),
            8,
        )
        if cost_estimated
        else None
    )

    summary.update(
        {
            "schema_version": EVENT_SCHEMA_VERSION,
            "run_id": state.get("run_id"),
            "job_id": state.get("job_id"),
            "project_name": state.get("project_name"),
            "target_stack": state.get("target_stack", "both"),
            "status": status,
            "current_phase": state.get("current_phase", "intake"),
            "event_count": int(summary.get("event_count", 0)) + 1,
            "last_sequence": event.get("sequence"),
            "step_attempts": int(summary.get("step_attempts", 0)) + int(step_finished),
            "succeeded_steps": int(summary.get("succeeded_steps", 0))
            + int(step_finished and event.get("status") == "succeeded"),
            "failed_steps": failed_steps,
            "action_items": action_items,
            "input_tokens": int(summary.get("input_tokens", 0))
            + (0 if usage_detail else int(event.get("input_tokens") or 0)),
            "output_tokens": int(summary.get("output_tokens", 0))
            + (0 if usage_detail else int(event.get("output_tokens") or 0)),
            "cached_tokens": int(summary.get("cached_tokens", 0))
            + (0 if usage_detail else int(event.get("cached_tokens") or 0)),
            "reasoning_tokens": int(summary.get("reasoning_tokens", 0))
            + (0 if usage_detail else int(event.get("reasoning_tokens") or 0)),
            "estimated_cost": estimated_cost,
            "cost_estimated": cost_estimated,
            "started_at": summary.get("started_at")
            or (event.get("started_at") if event_type == "run_started" else None),
            "ended_at": (
                event.get("ended_at")
                if event_type == "run_finished"
                else summary.get("ended_at")
            ),
            "last_event_at": event.get("timestamp"),
            "updated_at": _utc_now(),
        }
    )
    _atomic_json(summary_path, summary)
    return summary


def append_event(state: dict[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    """Append one normalized event and update the derived run summary."""
    paths = ensure_run_layout(state)
    run_dir = Path(paths["run_dir"])
    events_path = Path(paths["events_path"])
    with _event_file_lock(run_dir):
        sequence = _last_sequence(events_path) + 1
        normalized = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": f"event-{uuid4().hex}",
            "event_type": "event",
            "sequence": sequence,
            "timestamp": _utc_now(),
            "run_id": state.get("run_id"),
            "job_id": state.get("job_id"),
            "trace_id": state.get("run_id"),
            "span_id": None,
            "parent_span_id": None,
            "step_id": None,
            "parent_step_id": None,
            "phase": state.get("current_phase"),
            "node": None,
            "stack": state.get("target_stack", "both"),
            "spec_id": state.get("current_spec_id"),
            "task_id": state.get("current_task_id"),
            "requirement_id": (state.get("requirements") or {}).get("id"),
            "acceptance_criterion_id": state.get("acceptance_criterion_id"),
            "attempt": None,
            "status": None,
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "model": None,
            "model_request_id": None,
            "prompt_version": None,
            "prompt_hash": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "visible_output_tokens": 0,
            "finish_reason": None,
            "total_tokens": 0,
            "estimated_cost": None,
            "input_artifacts": [],
            "output_artifacts": [],
            "artifact_hashes": {},
            "files_changed": [],
            "command": None,
            "exit_code": None,
            "retry_reason": None,
            "verification_check": None,
            "expected": None,
            "actual": None,
            "severity": None,
            "suggested_fix": None,
            "error_type": None,
            "error_message": None,
            "stack_trace": None,
            "step_report": None,
            "worker_id": os.getenv("WORKER_ID"),
            "queue_job_id": state.get("queue_job_id"),
            **dict(event),
        }
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact(normalized), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        summary = _update_summary(state, paths, normalized)
        write_run_views(state, paths, summary, _read_events(events_path))
    return normalized


def initialize_run_observability(state: dict[str, Any]) -> dict[str, str]:
    """Initialize run metadata and emit exactly one run-start event."""
    paths = ensure_run_layout(state)
    metadata_path = Path(paths["run_metadata_path"])
    if not metadata_path.exists():
        workspace_root = str(
            (state.get("artifacts") or {}).get("workspace_root", Path.cwd())
        )
        metadata = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "run_id": state.get("run_id"),
            "job_id": state.get("job_id"),
            "project_name": state.get("project_name"),
            "target_stack": state.get("target_stack", "both"),
            "input_type": state.get("input_type", "prompt"),
            "request_hash": hashlib.sha256(
                str(state.get("raw_request") or state.get("user_prompt") or "").encode(
                    "utf-8"
                )
            ).hexdigest(),
            "created_at": state.get("created_at") or _utc_now(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            **_git_metadata(workspace_root),
        }
        _atomic_json(metadata_path, metadata)

    if Path(paths["events_path"]).stat().st_size == 0:
        append_event(
            state,
            {
                "event_type": "run_started",
                "status": "running",
                "started_at": state.get("created_at") or _utc_now(),
                "node": "workflow",
                "step_id": "workflow",
            },
        )
    return paths


def _existing_files(value: Any, *, limit: int = 250) -> list[str]:
    found: list[str] = []

    def visit(item: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(item, Mapping):
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple, set)):
            for child in item:
                visit(child)
        elif isinstance(item, (str, Path)):
            try:
                candidate = Path(item).expanduser()
                if candidate.is_file():
                    resolved = str(candidate.resolve())
                    if resolved not in found:
                        found.append(resolved)
            except (OSError, TypeError, ValueError):
                return

    visit(value)
    return found


def _artifact_hashes(paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in paths:
        try:
            hashes[path] = sha256_file(path)
        except OSError:
            continue
    return hashes


def _register_artifacts(
    state: dict[str, Any], paths_to_register: list[str], active: ActiveStep
) -> None:
    paths = ensure_run_layout(state)
    manifest_path = Path(paths["artifact_manifest_path"])
    with _event_file_lock(Path(paths["run_dir"])):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {
                "schema_version": EVENT_SCHEMA_VERSION,
                "run_id": active.run_id,
                "artifacts": [],
            }
        artifacts = list(manifest.get("artifacts", []))
        known = {
            (item.get("path"), item.get("sha256"))
            for item in artifacts
            if isinstance(item, dict)
        }
        for item_path in paths_to_register:
            path = Path(item_path)
            if not path.is_file():
                continue
            digest = sha256_file(path)
            if (str(path), digest) in known:
                continue
            artifacts.append(
                {
                    "path": str(path),
                    "sha256": digest,
                    "size_bytes": path.stat().st_size,
                    "step_id": active.step_id,
                    "attempt": active.attempt,
                    "recorded_at": _utc_now(),
                }
            )
        manifest["artifacts"] = artifacts
        manifest["updated_at"] = _utc_now()
        _atomic_json(manifest_path, manifest)


def record_step_artifact(filename: str, content: Any) -> str | None:
    """Persist a readable companion artifact for the active step."""
    active = _ACTIVE_STEP.get()
    if active is None:
        return None
    safe_name = Path(filename).name
    suffixes = {
        "prompt.txt": "prompt.md",
        "response.json": "response.md",
        "stderr.log": "error.log",
    }
    suffix = suffixes.get(safe_name)
    artifact_kind = safe_name
    dynamic = re.fullmatch(
        r"((?:task-\d+|repair-\d+(?:-(?:python|nodejs))?)-(?:prompt\.txt|response\.json))",
        safe_name,
    )
    if suffix is None and dynamic:
        artifact_kind = "prompt.txt" if safe_name.endswith("prompt.txt") else "response.json"
        suffix = safe_name.replace(".txt", ".md").replace(".json", ".md")
    if suffix is None:
        raise ValueError(f"Unsupported step artifact: {filename}")
    target = active.report_path.parent / f"{active.artifact_stem}-{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if artifact_kind in {"prompt.txt", "response.json"}:
        rendered = render_model_artifact(
            artifact_kind,
            redact(content),
            step_id=active.step_id,
            attempt=active.attempt,
        )
        target.write_text(_redact_text(rendered).rstrip() + "\n", encoding="utf-8")
    else:
        target.write_text(_redact_text(str(content)).rstrip() + "\n", encoding="utf-8")
    _register_artifacts(active.state, [str(target)], active)
    return str(target)


def _reserve_step_report(
    paths: Mapping[str, str], step_id: str
) -> tuple[int, Path, str]:
    """Reserve a stable, ordered Markdown report name for one step attempt."""
    index_path = Path(paths["machine_dir"]) / "step-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {"next_ordinal": 1, "attempts": {}}
    attempts = dict(index.get("attempts") or {})
    attempt = int(attempts.get(step_id, 0)) + 1
    ordinal = int(index.get("next_ordinal", 1))
    attempts[step_id] = attempt
    index.update({"next_ordinal": ordinal + 1, "attempts": attempts})
    _atomic_json(index_path, index)

    attempt_suffix = f"-attempt-{attempt}" if attempt > 1 else ""
    artifact_stem = f"{ordinal:02d}-{step_slug(step_id)}{attempt_suffix}"
    report_path = Path(paths["steps_dir"]) / f"{artifact_stem}.md"
    return attempt, report_path, artifact_stem


def _step_stack(step_id: str, state: Mapping[str, Any]) -> str:
    if step_id == "python_builder":
        return "python"
    if step_id == "nodejs_builder":
        return "nodejs"
    return str(state.get("target_stack", "both"))


def _start_step(
    state: dict[str, Any], step_id: str, parent_step_id: str | None
) -> ActiveStep:
    paths = initialize_run_observability(state)
    with _event_file_lock(Path(paths["run_dir"])):
        attempt, report_path, artifact_stem = _reserve_step_report(paths, step_id)
    input_artifacts = _existing_files(
        {
            "checkpoint_path": state.get("checkpoint_path"),
            "requirements": state.get("requirements"),
            "architecture_plan": state.get("architecture_plan"),
            "spec_tree": state.get("spec_tree"),
            "execution_plan": state.get("execution_plan"),
        }
    )
    active = ActiveStep(
        run_id=str(state["run_id"]),
        step_id=step_id,
        parent_step_id=parent_step_id,
        attempt=attempt,
        span_id=f"span-{uuid4().hex}",
        report_path=report_path,
        artifact_stem=artifact_stem,
        started_at=_utc_now(),
        started_monotonic=time.perf_counter(),
        input_artifacts=input_artifacts,
        state=state,
    )
    active.context_token = _ACTIVE_STEP.set(active)
    write_step_started(
        report_path,
        step_id=step_id,
        parent_step_id=parent_step_id,
        attempt=attempt,
        started_at=active.started_at,
        input_artifacts=active.input_artifacts,
    )
    registered = active.input_artifacts
    _register_artifacts(state, registered, active)
    append_event(
        state,
        {
            "event_type": "step_started",
            "step_id": step_id,
            "parent_step_id": parent_step_id,
            "node": step_id,
            "stack": _step_stack(step_id, state),
            "attempt": attempt,
            "span_id": active.span_id,
            "status": "started",
            "started_at": active.started_at,
            "step_report": str(report_path),
            "input_artifacts": active.input_artifacts,
            "artifact_hashes": _artifact_hashes(active.input_artifacts),
        },
    )
    return active


def _model_metadata(result: Mapping[str, Any], step_id: str) -> dict[str, Any]:
    candidates: list[Any] = []
    if step_id == "comparison":
        candidates.append(result.get("comparison_metadata"))
    elif step_id == "python_builder":
        output = result.get("python_output")
        candidates.append(
            output.get("observability") if isinstance(output, Mapping) else None
        )
    elif step_id == "nodejs_builder":
        output = result.get("nodejs_output")
        candidates.append(
            output.get("observability") if isinstance(output, Mapping) else None
        )
    elif step_id == "targeted_repair":
        history = result.get("repair_history")
        latest = history[-1] if isinstance(history, list) and history else None
        if isinstance(latest, Mapping):
            for record in latest.get("records", []):
                if isinstance(record, Mapping):
                    candidates.append(record.get("observability"))
    valid = [dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)]
    if not valid:
        return {}
    if len(valid) == 1:
        return valid[0]
    aggregate = dict(valid[-1])
    aggregate["model_calls"] = len(valid)
    aggregate["model_request_ids"] = [
        item.get("model_request_id") for item in valid if item.get("model_request_id")
    ]
    for key in (
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "total_tokens",
        "estimated_cost",
    ):
        values = [item.get(key) for item in valid if isinstance(item.get(key), (int, float))]
        aggregate[key] = sum(values) if values else None
    return aggregate


def _business_outcome(
    result: Mapping[str, Any],
    step_id: str,
) -> tuple[str, str | None, str | None, str | None]:
    # Reporting a failed run is still a successful reporting step. The actual
    # failure is already attached to the step that caused it.
    if step_id == "generate_report":
        return "succeeded", None, None, None

    output_keys = {
        "python_builder": ("python_output",),
        "nodejs_builder": ("nodejs_output",),
        "comparison": ("comparison_metadata",),
    }.get(step_id, ())
    for key in output_keys:
        output = result.get(key)
        if not isinstance(output, Mapping):
            continue
        status = str(output.get("status") or "")
        if status == "failed":
            message = str(
                output.get("error") or output.get("message") or f"{key} failed"
            )
            return (
                "failed",
                "AgentResultError",
                message,
                "Inspect the model response and retry this step after correcting the reported error.",
            )
        if status == "placeholder":
            message = str(output.get("message") or "Model execution was skipped")
            return (
                "skipped",
                None,
                message,
                "Configure OPENAI_API_KEY to execute the model-backed step.",
            )

    if result.get("job_status") == "blocked":
        return (
            "blocked",
            "VerificationBlocked",
            "The workflow is blocked by verification.",
            "Review failed verification checks and repair the referenced artifacts.",
        )
    if step_id == "quality_gate":
        quality = result.get("quality_results")
        if isinstance(quality, Mapping) and not quality.get("passed"):
            failures = [
                f"{stack.get('stack')}:{check.get('category')}"
                for stack in quality.get("stacks", [])
                if isinstance(stack, Mapping)
                for check in stack.get("checks", [])
                if isinstance(check, Mapping) and check.get("status") == "failed"
            ]
            return (
                "failed",
                "QualityGateFailed",
                f"Failed checks: {', '.join(failures) or 'generation'}",
                "Inspect the quality report; the workflow will attempt a targeted repair.",
            )
    if step_id == "targeted_repair":
        history = result.get("repair_history")
        latest = history[-1] if isinstance(history, list) and history else None
        if isinstance(latest, Mapping) and latest.get("status") in {"failed", "partial"}:
            return (
                "failed",
                "TargetedRepairFailed",
                "The repair attempt did not patch every failing stack.",
                "Inspect the repair response and the failed quality command before the next attempt.",
            )
    if step_id == "traceability":
        traceability = result.get("traceability_result")
        if isinstance(traceability, Mapping) and not traceability.get("passed"):
            missing = [
                f"{item.get('id')}: {', '.join(item.get('missing', []))}"
                for item in traceability.get("criteria", [])
                if isinstance(item, Mapping) and item.get("missing")
            ]
            return (
                "failed",
                "TraceabilityGateFailed",
                "; ".join(missing) or "Requirement evidence is incomplete.",
                "Inspect reports/traceability.md and repair the missing contract, patch, or check evidence.",
            )
    if result.get("job_status") == "failed":
        errors = result.get("errors") or []
        return (
            "failed",
            "WorkflowStepError",
            "; ".join(map(str, errors)),
            "Review the step result and its input artifacts before retrying.",
        )
    return "succeeded", None, None, None


def _verification_details(result: Mapping[str, Any], step_id: str) -> dict[str, Any]:
    if step_id == "quality_gate":
        quality = result.get("quality_results")
        if not isinstance(quality, Mapping):
            return {}
        checks = [
            check
            for stack in quality.get("stacks", [])
            if isinstance(stack, Mapping)
            for check in stack.get("checks", [])
            if isinstance(check, Mapping)
        ]
        failed = [check for check in checks if check.get("status") == "failed"]
        first = failed[0] if failed else {}
        return {
            "verification_checks": checks,
            "verification_check": first.get("category", "all checks"),
            "expected": "all required quality checks pass",
            "actual": f"{len(failed)} failed check(s)",
            "severity": "error" if failed else "info",
            "command": first.get("command_display"),
            "exit_code": first.get("exit_code"),
            "retry_reason": (
                f"{first.get('stack')} {first.get('category')} failed"
                if first
                else None
            ),
        }
    if step_id not in {"verification", "repair"}:
        return {}
    history = result.get("verification_results")
    if not isinstance(history, list) or not history:
        return {}
    latest = history[-1]
    if not isinstance(latest, Mapping):
        return {}
    checks = latest.get("checks") if isinstance(latest.get("checks"), list) else []
    failed = [
        check
        for check in checks
        if isinstance(check, Mapping) and not check.get("passed")
    ]
    return {
        "verification_checks": checks,
        "verification_check": failed[0].get("name") if failed else "all checks",
        "expected": "all verification checks pass",
        "actual": f"{len(failed)} failed check(s)",
        "severity": "error" if failed else "info",
    }


def _finish_step(
    state: dict[str, Any],
    active: ActiveStep,
    *,
    result: Mapping[str, Any] | None = None,
    exception: BaseException | None = None,
) -> None:
    result = dict(result or {})
    effective_state = {**state, **result}
    ended_at = _utc_now()
    duration_ms = round((time.perf_counter() - active.started_monotonic) * 1000, 3)

    stack_trace = None
    if exception is not None:
        status = "failed"
        error_type = type(exception).__name__
        error_message = str(exception)
        stack_trace = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        suggested_fix = "Inspect the linked error log and inputs, correct the root cause, then retry this step."
        record_step_artifact("stderr.log", stack_trace)
    else:
        status, error_type, error_message, suggested_fix = _business_outcome(
            result,
            active.step_id,
        )

    artifact_source: Mapping[str, Any] = result
    if active.step_id == "parse_input":
        artifact_source = {}
    elif active.step_id == "generate_report":
        artifact_source = {
            "delivery_summary_markdown": result.get("delivery_summary_markdown"),
            "final_checkpoint_path": result.get("final_checkpoint_path"),
            "comparison_report_markdown": (
                (result.get("artifacts") or {}).get("comparison_report_markdown")
                if isinstance(result.get("artifacts"), Mapping)
                else None
            ),
        }
    output_artifacts = _existing_files(artifact_source)
    for step_file in active.report_path.parent.glob(f"{active.artifact_stem}-*"):
        if step_file.is_file() and str(step_file) not in output_artifacts:
            output_artifacts.append(str(step_file))
    model = _model_metadata(result, active.step_id)
    write_step_finished(
        active.report_path,
        step_id=active.step_id,
        parent_step_id=active.parent_step_id,
        attempt=active.attempt,
        status=status,
        started_at=active.started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        input_artifacts=active.input_artifacts,
        output_artifacts=output_artifacts,
        result=result,
        model=model,
        error_type=error_type,
        error_message=error_message,
        suggested_fix=suggested_fix,
    )
    output_artifacts.append(str(active.report_path))
    _register_artifacts(effective_state, output_artifacts, active)
    append_event(
        effective_state,
        {
            "event_type": "step_finished",
            "step_id": active.step_id,
            "parent_step_id": active.parent_step_id,
            "node": active.step_id,
            "stack": _step_stack(active.step_id, effective_state),
            "attempt": active.attempt,
            "span_id": active.span_id,
            "status": status,
            "step_report": str(active.report_path),
            "started_at": active.started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "input_artifacts": active.input_artifacts,
            "output_artifacts": output_artifacts,
            "artifact_hashes": _artifact_hashes(output_artifacts),
            "files_changed": output_artifacts,
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "suggested_fix": suggested_fix,
            **model,
            **_verification_details(result, active.step_id),
        },
    )


def finish_run(state: dict[str, Any]) -> None:
    """Emit the terminal run event once and refresh the summary."""
    paths = initialize_run_observability(state)
    events = _read_events(Path(paths["events_path"]))
    if any(event.get("event_type") == "run_finished" for event in events):
        return
    started_event = next(
        (event for event in events if event.get("event_type") == "run_started"), {}
    )
    duration_ms = None
    try:
        started = datetime.fromisoformat(str(started_event.get("started_at")))
        duration_ms = round(
            (datetime.now(timezone.utc) - started).total_seconds() * 1000, 3
        )
    except (TypeError, ValueError):
        pass
    append_event(
        state,
        {
            "event_type": "run_finished",
            "node": "workflow",
            "step_id": "workflow",
            "status": state.get("job_status", "completed"),
            "started_at": started_event.get("started_at"),
            "ended_at": _utc_now(),
            "duration_ms": duration_ms,
        },
    )


def instrument_node(
    step_id: str,
    node: Callable[[Any], Any],
    *,
    parent_step_id: str | None = None,
) -> Callable[[Any], Any]:
    """Wrap a synchronous LangGraph node with step-attempt observability."""

    @wraps(node)
    def observed(state: dict[str, Any]) -> Any:
        active = _start_step(state, step_id, parent_step_id)
        try:
            result = node(state)
        except BaseException as error:
            _finish_step(state, active, exception=error)
            raise
        else:
            result_mapping = (
                result if isinstance(result, Mapping) else {"result": result}
            )
            _finish_step(state, active, result=result_mapping)
            effective_state = {**state, **result_mapping}
            if step_id == "generate_report" and effective_state.get("job_status") in {
                "completed",
                "failed",
                "blocked",
            }:
                finish_run(effective_state)
            return result
        finally:
            if active.context_token is not None:
                _ACTIVE_STEP.reset(active.context_token)

    return observed
