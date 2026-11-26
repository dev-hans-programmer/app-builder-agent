"""
Requirement analysis agent.

This module converts a raw user prompt or PRD into a structured requirement
artifact that downstream phases can use for architecture planning and spec
decomposition.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from src.graph.runtime import RequirementArtifact, ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


COMPLEX_KEYWORDS = {
    "microservice",
    "microservices",
    "websocket",
    "real-time",
    "realtime",
    "payments",
    "payment",
    "billing",
    "queue",
    "worker",
    "scheduler",
    "event-driven",
    "streaming",
    "multi-tenant",
    "multi tenant",
    "oauth",
    "authentication",
    "authorization",
    "graphql",
}

MEDIUM_KEYWORDS = {
    "auth",
    "database",
    "crud",
    "dashboard",
    "admin",
    "email",
    "cache",
    "logging",
    "analytics",
    "upload",
    "search",
}

NON_FUNCTIONAL_KEYWORDS = {
    "secure": "security",
    "security": "security",
    "scalable": "scalability",
    "scalability": "scalability",
    "fast": "performance",
    "performance": "performance",
    "reliable": "reliability",
    "observability": "observability",
    "monitor": "observability",
    "production": "production-readiness",
    "maintainable": "maintainability",
    "testable": "testability",
}


def detect_input_type(raw_request: str) -> str:
    """
    Detect the input type from the raw request.

    Returns one of: prompt, prd, brief, feature_list.
    """
    text = raw_request.strip().lower()
    line_count = len([line for line in text.splitlines() if line.strip()])

    if any(marker in text for marker in ("prd", "problem statement", "goals", "non-goals")):
        return "prd"
    if any(marker in text for marker in ("feature list", "user stories", "acceptance criteria")):
        return "feature_list"
    if line_count >= 6 or any(marker in text for marker in ("overview", "requirements", "# ", "## ")):
        return "brief"
    return "prompt"


def classify_complexity(text: str, functional_requirements: Iterable[str] | None = None) -> str:
    """
    Classify the request as simple, medium, or complex.
    """
    normalized = text.lower()
    func_count = len(list(functional_requirements or []))
    complex_hits = sum(1 for keyword in COMPLEX_KEYWORDS if keyword in normalized)
    medium_hits = sum(1 for keyword in MEDIUM_KEYWORDS if keyword in normalized)
    word_count = len(re.findall(r"\w+", normalized))

    if complex_hits >= 1 or word_count > 120 or func_count >= 6:
        return "complex"
    if medium_hits >= 1 or word_count > 50 or func_count >= 3:
        return "medium"
    return "simple"


def _extract_goals(text: str) -> list[str]:
    goals: list[str] = []
    normalized = text.strip()
    if normalized:
        first_sentence = re.split(r"[.!?]\s+", normalized, maxsplit=1)[0]
        goals.append(first_sentence)
    return goals


def _extract_functional_requirements(text: str) -> list[str]:
    clauses = re.split(r"[.\n;]+", text)
    requirements = []
    for clause in clauses:
        item = clause.strip(" -\t")
        if not item:
            continue
        lower = item.lower()
        if any(
            keyword in lower
            for keyword in (
                "build",
                "create",
                "support",
                "allow",
                "enable",
                "crud",
                "list",
                "manage",
                "search",
                "authenticate",
                "authorize",
                "upload",
                "notify",
            )
        ):
            requirements.append(item)
    return requirements or [text.strip()]


def _extract_non_functional_requirements(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(
        {label for keyword, label in NON_FUNCTIONAL_KEYWORDS.items() if keyword in lowered}
    )


def _extract_constraints(text: str) -> list[str]:
    constraints = []
    lowered = text.lower()
    if "must use" in lowered or "use " in lowered:
        constraints.append(text.strip())
    if any(language in lowered for language in ("fastapi", "express", "python", "node.js")):
        constraints.append("Specific implementation stack was mentioned.")
    return constraints


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _build_assumptions(text: str) -> list[str]:
    lowered = text.lower()
    assumptions = []
    if not _contains_any(lowered, ("database", "storage", "persist", "persistence", "in-memory", "in memory", "inmememory")):
        assumptions.append("Persistence strategy is not specified yet.")
    if not any(marker in lowered for marker in ("auth", "authentication", "authorization", "login")):
        assumptions.append("Authentication requirements are not fully specified yet.")
    if not any(marker in lowered for marker in ("deploy", "deployment", "hosting", "production")):
        assumptions.append("Deployment target and hosting strategy are not specified yet.")
    return assumptions


def _build_problem_statement(text: str) -> str:
    summary = text.strip()
    if not summary:
        return "The problem statement was not provided."
    first_sentence = re.split(r"[.!?]\s+", summary, maxsplit=1)[0].strip()
    return first_sentence or summary


def _build_target_users(text: str) -> list[str]:
    lowered = text.lower()
    users: list[str] = []
    if any(marker in lowered for marker in ("admin", "dashboard", "manage", "workspace", "project")):
        users.append("Internal operators and workspace administrators")
    if any(marker in lowered for marker in ("user", "customer", "member", "team")):
        users.append("End users interacting with the product")
    if not users:
        users.append("Primary product users")
    return users


def _build_success_criteria(functional_requirements: list[str], complexity: str) -> list[str]:
    criteria = [
        "The generated solution covers the documented functional requirements.",
        "The artifact set is sufficient to plan implementation without losing context.",
    ]
    if complexity != "simple":
        criteria.append("Clarification questions are resolved before architecture planning continues.")
    if len(functional_requirements) > 1:
        criteria.append("The PRD remains readable and organized even when multiple capabilities are requested.")
    return criteria


def _build_open_questions(text: str) -> list[str]:
    lowered = text.lower()
    questions = []
    if _contains_any(lowered, ("in-memory", "in memory", "inmememory", "ephemeral", "volatile")):
        questions.append("Should this in-memory data reset on every restart, or should we persist it later?")
    elif not _contains_any(lowered, ("database", "storage", "persist", "persistence")):
        questions.append("Do you want this data to remain in-memory, or should we use a persistence layer?")

    if _contains_any(lowered, ("link", "linked", "associate", "relationship", "belongs to", "belongs", "parent", "child")) or (
        "user" in lowered and _contains_any(lowered, ("post", "comment", "task", "project", "order", "item"))
    ):
        if "user" in lowered and "post" in lowered:
            questions.append("Should posts attach to an existing userId, and what should happen if that user is deleted?")
        else:
            questions.append("What is the ownership or cardinality rule between the linked resources?")

    if not _contains_any(lowered, ("auth", "authentication", "authorization", "login")):
        questions.append("Should this API require authentication or authorization?")

    if not _contains_any(lowered, ("deploy", "deployment", "hosting", "production")):
        questions.append("Where should this service be deployed, and are there environment constraints?")

    if (
        not questions
        and classify_complexity(text, _extract_functional_requirements(text)) == "complex"
        and _contains_any(lowered, ("production", "scale", "reliable", "observability", "logging", "monitor"))
    ):
        questions.append("Do you want observability hooks such as logging, metrics, or tracing from day one?")
    return questions


def _render_bullets(items: list[str]) -> list[str]:
    """Render list items as markdown bullets, with a fallback when empty."""
    return [f"- {item}" for item in items] if items else ["- None captured"]


def build_requirement_artifact(
    raw_request: str,
    project_name: str,
    input_type: str | None = None,
) -> RequirementArtifact:
    """
    Build a structured requirement artifact from a raw request.
    """
    detected_type = input_type or detect_input_type(raw_request)
    functional_requirements = _extract_functional_requirements(raw_request)
    non_functional_requirements = _extract_non_functional_requirements(raw_request)
    complexity = classify_complexity(raw_request, functional_requirements)

    return RequirementArtifact(
        id=f"{project_name}-requirements",
        title=f"Requirements for {project_name}",
        source_type=detected_type,
        summary=raw_request.strip(),
        goals=_extract_goals(raw_request),
        functional_requirements=functional_requirements,
        non_functional_requirements=non_functional_requirements,
        constraints=_extract_constraints(raw_request),
        assumptions=_build_assumptions(raw_request),
        open_questions=_build_open_questions(raw_request),
        out_of_scope=[],
        complexity=complexity,
        created_at="",
    )


def render_requirements_markdown(requirements: RequirementArtifact) -> str:
    """
    Render the requirement artifact as markdown.
    """
    clarification_answers = requirements.get("clarification_answers", [])
    clarification_lines = []
    if clarification_answers:
        for item in clarification_answers:
            question = item.get("question", "")
            answer = item.get("answer", "")
            clarification_lines.append(f"- **Q:** {question}")
            clarification_lines.append(f"  **A:** {answer}")

    sections = [
        "# Requirements Summary",
        "",
        f"**ID**: {requirements['id']}",
        f"**Title**: {requirements['title']}",
        f"**Source Type**: {requirements['source_type']}",
        f"**Complexity**: {requirements['complexity']}",
        "",
        "## Problem Statement",
        _build_problem_statement(str(requirements["summary"])),
        "",
        "## Target Users",
        *_render_bullets(_build_target_users(str(requirements["summary"]))),
        "",
        "## Summary",
        requirements["summary"],
        "",
        "## Goals",
        *_render_bullets(list(requirements.get("goals", []))),
        "",
        "## Functional Requirements",
        *_render_bullets(list(requirements.get("functional_requirements", []))),
        "",
        "## Non-Functional Requirements",
        *_render_bullets(list(requirements.get("non_functional_requirements", []))),
        "",
        "## Constraints",
        *_render_bullets(list(requirements.get("constraints", []))),
        "",
        "## Assumptions",
        *_render_bullets(list(requirements.get("assumptions", []))),
        "",
        "## Success Criteria",
        *_render_bullets(
            _build_success_criteria(
                list(requirements.get("functional_requirements", [])),
                str(requirements.get("complexity", "simple")),
            )
        ),
        "",
        "## Open Questions",
        *_render_bullets(list(requirements.get("open_questions", []))),
        "",
    ]

    if clarification_lines:
        sections.extend(
            [
                "## Clarification Answers",
                *clarification_lines,
                "",
            ]
        )

    return "\n".join(sections)


def persist_requirement_artifacts(
    requirements: RequirementArtifact,
    manifest: Dict[str, str],
    job_id: str,
) -> Dict[str, str]:
    """
    Persist the PRD artifact as a single markdown file.
    """
    requirements_dir = Path(manifest["requirements_dir"])
    requirements_dir.mkdir(parents=True, exist_ok=True)

    prd_path = requirements_dir / "prd.md"
    prd_path.write_text(render_requirements_markdown(requirements), encoding="utf-8")

    stale_questions_path = requirements_dir / "open-questions.md"
    if stale_questions_path.exists() and not requirements.get("open_questions"):
        stale_questions_path.unlink()

    return {
        "prd_markdown": str(prd_path),
        "requirements_markdown": str(prd_path),
        "requirements_json": str(prd_path),
        "open_questions_markdown": str(prd_path) if requirements.get("open_questions") else "",
        "clarification_answers_markdown": "",
        "clarification_answers_json": "",
    }


def analyze_requirements(state: BuilderState) -> Dict[str, Any]:
    """
    Analyze raw input and persist the requirement artifacts.
    """
    raw_request = state.get("raw_request") or state["user_prompt"]
    project_name = state["project_name"]
    artifact_manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    requirements = build_requirement_artifact(raw_request, project_name, state.get("input_type"))
    requirements["created_at"] = state.get("timestamp", "")
    artifact_paths = persist_requirement_artifacts(requirements, artifact_manifest, state["job_id"])

    updates = {
        "requirements": {
            **requirements,
            "artifact_paths": artifact_paths,
            "needs_clarification": bool(requirements.get("open_questions")),
        },
        "input_type": requirements["source_type"],
        "job_status": "running",
        "current_phase": "requirement_analysis",
        "artifacts": artifact_manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, artifact_manifest, suffix="requirement_analysis")
    )
    return updates
