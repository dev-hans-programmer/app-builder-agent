"""
Clarification gate agent.

This module asks clarification questions directly in the terminal, persists a
single compact clarification artifact, and merges the answers back into the
requirement artifact before the workflow continues.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from rich.console import Console

from src.agents.requirement_analyst import persist_requirement_artifacts
from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


console = Console()


def _responses_from_payload(payload: Any) -> list[dict[str, str]]:
    """Normalize clarification response payloads into question/answer records."""
    if isinstance(payload, dict):
        if "responses" in payload and isinstance(payload["responses"], list):
            payload = payload["responses"]
        elif "answers" in payload and isinstance(payload["answers"], list):
            payload = payload["answers"]
        else:
            payload = [
                {"question": question, "answer": answer}
                for question, answer in payload.items()
                if isinstance(question, str)
            ]

    responses: list[dict[str, str]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                question = str(item.get("question", "")).strip()
                answer = str(item.get("answer", "")).strip()
                if question:
                    responses.append({"question": question, "answer": answer})
    return responses


def _response_template(requirements: Dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"question": question, "answer": ""}
        for question in requirements.get("open_questions", [])
    ]


def _clarification_path(requirements_dir: str | Path) -> Path:
    base = Path(requirements_dir)
    return base / "clarification.md"


def _prompt_for_clarifications(questions: list[str]) -> list[dict[str, str]]:
    """Ask clarification questions directly in the terminal."""
    responses: list[dict[str, str]] = []
    if not questions:
        return responses

    console.print()
    console.print(
        "[bold cyan]Clarification needed.[/bold cyan] Answer the following questions and the workflow will continue immediately."
    )
    console.print()

    for index, question in enumerate(questions, start=1):
        answer = console.input(f"[bold yellow]{index}. {question}[/bold yellow] ")
        responses.append({"question": question, "answer": answer.strip()})

    return responses


def _merge_clarifications(
    requirements: Dict[str, Any],
    responses: list[dict[str, str]],
) -> Dict[str, Any]:
    open_questions = list(requirements.get("open_questions", []))
    response_map = {
        item["question"]: item.get("answer", "").strip()
        for item in responses
        if item["question"]
    }

    resolved: list[dict[str, str]] = []
    pending: list[str] = []
    for question in open_questions:
        answer = response_map.get(question, "").strip()
        if answer:
            resolved.append({"question": question, "answer": answer})
        else:
            pending.append(question)

    merged = dict(requirements)
    merged["clarification_answers"] = resolved
    merged["open_questions"] = pending
    merged["needs_clarification"] = bool(pending)
    merged["clarification_resolved"] = not pending
    return merged


def load_clarification_responses(
    requirements_dir: str | Path,
    job_id: str,
) -> list[dict[str, str]]:
    """Load clarification responses from the single clarification artifact if present."""
    clarification_path = _clarification_path(requirements_dir)
    legacy_path = Path(requirements_dir) / "clarification.json"
    if not clarification_path.exists() and not legacy_path.exists():
        return []
    if not clarification_path.exists() and legacy_path.exists():
        clarification_path = legacy_path

    try:
        text = clarification_path.read_text(encoding="utf-8")
    except OSError:
        return []

    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            import json

            payload = json.loads(text)
        except Exception:
            return []
        return _responses_from_payload(payload)

    payload_lines = []
    current_question = None
    current_answer = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Q:"):
            if current_question is not None:
                payload_lines.append(
                    {"question": current_question, "answer": current_answer or ""}
                )
            current_question = stripped.removeprefix("- Q:").strip()
            current_answer = ""
        elif stripped.startswith("A:") or stripped.startswith("- A:"):
            current_answer = stripped.split(":", 1)[1].strip()
    if current_question is not None:
        payload_lines.append(
            {"question": current_question, "answer": current_answer or ""}
        )

    return payload_lines


def create_clarification_template(
    requirements: Dict[str, Any],
    manifest: Dict[str, str],
    job_id: str,
    responses: list[dict[str, str]] | None = None,
) -> Dict[str, str]:
    """Write the single clarification artifact."""
    requirements_dir = manifest["requirements_dir"]
    clarification_path = _clarification_path(requirements_dir)
    response_template = (
        responses if responses is not None else _response_template(requirements)
    )
    answered_count = sum(
        1 for item in response_template if item.get("answer", "").strip()
    )
    lines = [
        "# Clarification",
        "",
        f"**Job**: {job_id}",
        "",
        f"**Status**: {'answered' if responses else 'pending'}",
        f"**Answered**: {answered_count}/{len(response_template)}",
        "",
        "## Open Questions",
    ]
    lines.extend(f"- {question}" for question in requirements.get("open_questions", []))
    lines.extend(["", "## Answers"])
    for item in response_template:
        lines.append(f"- Q: {item['question']}")
        lines.append(f"  A: {item.get('answer', '')}")
    lines.append("")
    clarification_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "clarification_markdown": str(clarification_path),
        "clarification_json": str(clarification_path),
    }


def clarify_requirements(state: BuilderState) -> Dict[str, Any]:
    """Ask clarification questions in the terminal and continue immediately."""
    if not state.get("clarification_gate_enabled", True):
        manifest = state.get("artifacts") or ensure_workspace_layout(
            ".",
            project_name=state.get("project_name"),
        )
        updates = {
            "job_status": "running",
            "current_phase": "architecture_planning",
            "artifacts": manifest,
        }
        updates["checkpoint_path"] = str(
            persist_job_checkpoint(
                {**state, **updates}, manifest, suffix="clarification_gate"
            )
        )
        return updates

    requirements = dict(state.get("requirements") or {})
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    job_id = state["job_id"]
    open_questions = list(requirements.get("open_questions", []))

    if not open_questions:
        clarification_path = _clarification_path(manifest["requirements_dir"])
        if clarification_path.exists():
            clarification_path.unlink()
        updates = {
            "job_status": "running",
            "current_phase": "architecture_planning",
            "artifacts": manifest,
        }
        updates["checkpoint_path"] = str(
            persist_job_checkpoint(
                {**state, **updates}, manifest, suffix="clarification_gate"
            )
        )
        return updates

    raw_responses = state.get("clarification_answers")
    responses = _responses_from_payload(raw_responses) if raw_responses else []
    if not responses:
        responses = load_clarification_responses(
            manifest["requirements_dir"],
            job_id,
        )
    if not responses:
        responses = _prompt_for_clarifications(open_questions)

    merged_requirements = _merge_clarifications(requirements, responses)
    clarification_artifact_requirements = dict(merged_requirements)
    clarification_artifact_requirements["open_questions"] = open_questions
    merged_requirements["open_questions"] = []
    merged_requirements["needs_clarification"] = False
    merged_requirements["clarification_resolved"] = True
    clarification_artifact_paths = create_clarification_template(
        clarification_artifact_requirements,
        manifest,
        job_id,
        responses,
    )
    merged_requirement_artifacts = persist_requirement_artifacts(
        merged_requirements, manifest, job_id
    )
    artifact_paths = {
        **merged_requirement_artifacts,
        **clarification_artifact_paths,
    }
    updates = {
        "requirements": {
            **merged_requirements,
            "artifact_paths": {
                **merged_requirements.get("artifact_paths", {}),
                **artifact_paths,
            },
        },
        "job_status": "running",
        "current_phase": "architecture_planning",
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint(
            {**state, **updates}, manifest, suffix="clarification_gate"
        )
    )
    return updates
