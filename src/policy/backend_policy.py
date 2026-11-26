"""Load, snapshot, and select sections from the Python production policy."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Iterable

from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


BACKEND_POLICY_PROMPT_VERSION = "1.0"
POLICY_ID = "python-production-backend"
MANDATORY_SECTIONS = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    17,
    18,
    19,
    20,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
]
CONDITIONAL_SECTIONS = [13, 14, 15, 16, 21]

TASK_SECTION_MAP: dict[str, list[int]] = {
    "foundation": [1, 3, 4, 18, 23, 24, 25, 26, 31, 32, 34, 35, 36],
    "platform": [2, 6, 7, 8, 9, 10, 11, 12, 18, 19, 20, 23, 27, 33, 35, 36],
    "authentication": [2, 5, 6, 7, 8, 9, 10, 11, 17, 22, 30, 33, 35, 36],
    "feature": [2, 5, 6, 7, 8, 9, 10, 11, 12, 21, 22, 23, 28, 29, 30, 33, 34, 35, 36],
    "delivery": [18, 19, 20, 22, 23, 24, 25, 26, 27, 31, 32, 33, 34, 35, 36],
    "repair": MANDATORY_SECTIONS,
    "review": list(range(1, 37)),
}

_SECTION_HEADING = re.compile(r"^(\d+)\.\s+(.+?)\s*$")


def _source_path() -> Path:
    configured_env = os.getenv("BACKEND_POLICY_PATH")
    configured = configured_env or "backend-prompt.md"
    path = Path(configured).expanduser().resolve()
    if not path.is_file() and configured_env is None:
        path = Path(__file__).resolve().parents[2] / "backend-prompt.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"Python backend policy not found: {path}. Set BACKEND_POLICY_PATH to a valid file."
        )
    return path


def _parse_sections(content: str) -> dict[str, dict[str, str]]:
    """Parse the numbered Markdown policy without interpreting its prose."""
    sections: dict[str, dict[str, str]] = {}
    current_number: str | None = None
    current_lines: list[str] = []
    current_title = ""

    def flush() -> None:
        if current_number is not None:
            sections[current_number] = {
                "title": current_title,
                "text": "\n".join(current_lines).strip(),
            }

    lines = content.splitlines()
    for index, line in enumerate(lines):
        match = _SECTION_HEADING.match(line)
        bounded_heading = bool(
            match
            and index > 0
            and index + 1 < len(lines)
            and lines[index - 1].strip().startswith("====")
            and lines[index + 1].strip().startswith("====")
        )
        if match and bounded_heading:
            flush()
            current_number = match.group(1)
            current_title = match.group(2)
            current_lines = [line]
        elif current_number is not None:
            current_lines.append(line)
    flush()
    missing = [str(number) for number in range(1, 37) if str(number) not in sections]
    if missing:
        raise ValueError(
            "Backend policy must contain numbered sections 1-36; "
            f"missing: {', '.join(missing)}."
        )
    return sections


def policy_sections(policy: dict[str, Any], section_numbers: Iterable[int]) -> str:
    """Return exact source text for selected policy sections."""
    sections = policy.get("sections") or {}
    selected = [
        sections[str(number)]["text"]
        for number in dict.fromkeys(section_numbers)
        if str(number) in sections
    ]
    return "\n\n".join(selected)


def policy_text_for_task(policy: dict[str, Any], task_kind: str) -> str:
    """Select the binding policy text relevant to one task or review."""
    section_numbers = TASK_SECTION_MAP.get(task_kind, MANDATORY_SECTIONS)
    header = (
        f"Backend policy: {policy.get('id', POLICY_ID)}\n"
        f"Policy version: {policy.get('version', '')}\n"
        f"Policy SHA-256: {policy.get('sha256', '')}\n"
        "The following rules are binding. Conditional components require explicit justification."
    )
    return f"{header}\n\n{policy_sections(policy, section_numbers)}"


def _render_policy_readme(policy: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Python Production Backend Policy",
            "",
            "This is the exact architecture policy used for this project run.",
            "",
            f"- Policy ID: `{policy['id']}`",
            f"- Version: `{policy['version']}`",
            f"- SHA-256: `{policy['sha256']}`",
            f"- Source: `{policy['source_path']}`",
            f"- Stack: `{policy['stack']}`",
            f"- Sections: {len(policy['sections'])}",
            "",
            "The adjacent `backend-prompt.md` is an immutable run snapshot.",
            "Changing the repository policy does not alter an in-progress run.",
            "",
        ]
    )


def load_backend_policy(state: BuilderState) -> dict[str, Any]:
    """Load and snapshot the canonical policy for Python generation only."""
    target_stack = state.get("target_stack", "both")
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".", project_name=state.get("project_name")
    )
    if target_stack not in {"python", "both"}:
        return {
            "backend_policy": {
                "enabled": False,
                "stack": "python",
                "reason": "The Python production policy is not applied to Node.js-only runs.",
            },
            "artifacts": manifest,
            "current_phase": "policy_loading",
            "job_status": "running",
        }

    source_path = _source_path()
    content = source_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    sections = _parse_sections(content)
    policy: dict[str, Any] = {
        "enabled": True,
        "id": POLICY_ID,
        "version": f"sha256:{digest[:12]}",
        "sha256": digest,
        "stack": "python",
        "source_path": str(source_path),
        "line_count": len(content.splitlines()),
        "sections": sections,
        "mandatory_sections": MANDATORY_SECTIONS,
        "conditional_sections": CONDITIONAL_SECTIONS,
        "prompt_version": BACKEND_POLICY_PROMPT_VERSION,
    }

    policy_dir = Path(manifest["policy_dir"])
    policy_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = policy_dir / "backend-prompt.md"
    snapshot_path.write_text(content, encoding="utf-8")
    readme_path = policy_dir / "README.md"
    readme_path.write_text(_render_policy_readme(policy), encoding="utf-8")
    policy["artifact_paths"] = {
        "policy_snapshot_markdown": str(snapshot_path),
        "policy_readme_markdown": str(readme_path),
    }
    manifest["policy_snapshot_markdown"] = str(snapshot_path)
    updates = {
        "backend_policy": policy,
        "artifacts": manifest,
        "current_phase": "policy_loading",
        "job_status": "running",
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, manifest, suffix="backend_policy")
    )
    return updates
