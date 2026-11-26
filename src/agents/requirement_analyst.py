"""
Requirement analysis agent.

This module converts a raw user prompt or PRD into a structured requirement
artifact that downstream phases can use for architecture planning and spec
decomposition.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from openai import OpenAI

from src.agents.model_request import chat_completion_options, completion_finish_reason
from src.graph.runtime import (
    RequirementArtifact,
    ensure_workspace_layout,
    persist_job_checkpoint,
)
from src.graph.state import BuilderState
from src.observability import record_step_artifact
from src.observability.model_usage import model_observability


REQUIREMENT_ANALYST_PROMPT_VERSION = "2.0"


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

    if any(
        marker in text for marker in ("prd", "problem statement", "goals", "non-goals")
    ):
        return "prd"
    if any(
        marker in text
        for marker in ("feature list", "user stories", "acceptance criteria")
    ):
        return "feature_list"
    if line_count >= 6 or any(
        marker in text for marker in ("overview", "requirements", "# ", "## ")
    ):
        return "brief"
    return "prompt"


def classify_complexity(
    text: str, functional_requirements: Iterable[str] | None = None
) -> str:
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
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", ". ", text)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", ". ", normalized)
    clauses = re.split(r"[.\n;]+", normalized)
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


def _extract_domain_entities(
    text: str, functional_requirements: Iterable[str] | None = None
) -> list[str]:
    """Extract conservative domain nouns without turning states or prose into resources."""
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).lower()
    normalized = " ".join([normalized, *(functional_requirements or [])]).lower()
    candidates: list[str] = []
    patterns = [
        r"\b([a-z][a-z0-9_-]*)\s+(?:backend|api|application|app|service)\b",
        r"\b(?:create|update|delete|view|list|search|filter|sort|paginate|manage|track|register)\s+(?:a|an|the|their|own|users?'?\s+own)*\s*([a-z][a-z0-9_-]*)\b",
    ]
    excluded = {
        "api",
        "application",
        "backend",
        "completed",
        "data",
        "description",
        "high",
        "incomplete",
        "low",
        "medium",
        "overdue",
        "pending",
        "priority",
        "profile",
        "service",
        "title",
    }
    for pattern in patterns:
        for candidate in re.findall(pattern, normalized):
            name = (
                candidate.removesuffix("ies") + "y"
                if candidate.endswith("ies")
                else candidate
            )
            if name.endswith("s") and not name.endswith("ss"):
                name = name[:-1]
            if name and name not in excluded and name not in candidates:
                candidates.append(name)
    if any(
        marker in normalized for marker in ("auth", "login", "register", "own data")
    ):
        candidates.insert(0, "user")
    return list(dict.fromkeys(candidates))


def _response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    content = getattr(choices[0].message, "content", "")
    return content if isinstance(content, str) else ""


def _json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Requirement analysis response did not contain a JSON object")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Requirement analysis response must be a JSON object")
    return payload


def _string_list(payload: dict[str, Any], name: str) -> list[str]:
    value = payload.get(name, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _model_requirement_analysis(
    raw_request: str, state: BuilderState
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Decompose requirements into atomic statements, with safe fallback."""
    policy = state.get("backend_policy") or {}
    enabled = (
        policy.get("enabled")
        and os.getenv("OPENAI_API_KEY")
        and os.getenv("REQUIREMENTS_MODEL_ENABLED", "true").lower()
        not in {"0", "false", "no", "off"}
    )
    if not enabled:
        return None, None, None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = f"""You are a senior product analyst. Decompose the submitted backend request into
atomic, independently testable requirements. Preserve every explicit capability and do not add
features. Repair missing whitespace or formatting when intent is clear.

Return JSON only with this exact shape:
{{
  "summary": "one concise problem statement",
  "goals": ["goal"],
  "functional_requirements": ["one observable capability per item"],
  "non_functional_requirements": ["one explicitly requested quality per item"],
  "domain_entities": ["singular business entity name, never an action, state, or attribute"],
  "constraints": ["explicit constraint"],
  "assumptions": ["only unavoidable assumption"],
  "out_of_scope": ["only explicitly excluded item"]
}}

Rules:
- Split compound clauses such as create/update/delete into separate capabilities when they can be tested separately.
- Include authentication, authorization, querying, pagination, and status behavior as separate items when requested.
- Do not choose libraries, databases, deployment targets, or architecture here.
- Do not collapse the entire request into one item.
- Domain entities are stable business objects such as User or Todo, not completed, priority, login, or pagination.

Submitted request:
{raw_request}
"""
    record_step_artifact("prompt.txt", prompt)
    options = chat_completion_options(model)
    try:
        response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **options,
        )
        content = _response_text(response)
        usage = model_observability(
            model=model,
            prompt=prompt,
            prompt_version=REQUIREMENT_ANALYST_PROMPT_VERSION,
            response=response,
        )
        usage.update(options)
        record_step_artifact(
            "response.json",
            {
                "id": getattr(response, "id", None),
                "model": getattr(response, "model", model),
                "content": content,
                "finish_reason": completion_finish_reason(response),
                "usage": usage,
            },
        )
        payload = _json_object(content)
        functional = _string_list(payload, "functional_requirements")
        if not functional:
            raise ValueError("Requirement analysis returned no functional requirements")
        normalized = {
            "summary": str(payload.get("summary") or raw_request).strip(),
            "goals": _string_list(payload, "goals"),
            "functional_requirements": functional,
            "non_functional_requirements": _string_list(
                payload, "non_functional_requirements"
            ),
            "constraints": _string_list(payload, "constraints"),
            "assumptions": _string_list(payload, "assumptions"),
            "out_of_scope": _string_list(payload, "out_of_scope"),
        }
        domain_entities = _string_list(payload, "domain_entities")
        if domain_entities:
            normalized["domain_entities"] = domain_entities
        return normalized, usage, None
    except Exception as exc:
        return (
            None,
            None,
            f"Structured requirement analysis failed; used deterministic fallback: {exc}",
        )


def _extract_non_functional_requirements(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(
        {
            label
            for keyword, label in NON_FUNCTIONAL_KEYWORDS.items()
            if keyword in lowered
        }
    )


def _extract_constraints(text: str) -> list[str]:
    constraints = []
    lowered = text.lower()
    if "must use" in lowered or "use " in lowered:
        constraints.append(text.strip())
    if any(language in lowered for language in ("fastapi", "python")):
        constraints.append("Specific implementation stack was mentioned.")
    return constraints


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _build_assumptions(text: str) -> list[str]:
    lowered = text.lower()
    assumptions = []
    if not _contains_any(
        lowered,
        (
            "database",
            "storage",
            "persist",
            "persistence",
            "in-memory",
            "in memory",
            "inmememory",
        ),
    ):
        assumptions.append("Persistence strategy is not specified yet.")
    if not any(
        marker in lowered
        for marker in ("auth", "authentication", "authorization", "login")
    ):
        assumptions.append("Authentication requirements are not fully specified yet.")
    if not any(
        marker in lowered
        for marker in ("deploy", "deployment", "hosting", "production")
    ):
        assumptions.append(
            "Deployment target and hosting strategy are not specified yet."
        )
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
    if any(
        marker in lowered
        for marker in ("admin", "dashboard", "manage", "workspace", "project")
    ):
        users.append("Internal operators and workspace administrators")
    if any(marker in lowered for marker in ("user", "customer", "member", "team")):
        users.append("End users interacting with the product")
    if not users:
        users.append("Primary product users")
    return users


def _build_success_criteria(functional_requirements: list[str]) -> list[str]:
    criteria = [
        "The generated solution covers the documented functional requirements.",
        "The artifact set is sufficient to plan implementation without losing context.",
    ]
    if len(functional_requirements) > 1:
        criteria.append(
            "The PRD remains readable and organized even when multiple capabilities are requested."
        )
    return criteria


def _build_acceptance_criteria(
    functional_requirements: list[str],
    non_functional_requirements: list[str],
) -> list[Dict[str, Any]]:
    """Turn every normalized requirement into a stable, testable contract."""
    criteria: list[Dict[str, Any]] = []
    for index, requirement in enumerate(functional_requirements, start=1):
        criteria.append(
            {
                "id": f"AC-{index:03d}",
                "requirement": requirement,
                "given": "the generated application is running",
                "when": f"a user exercises: {requirement}",
                "then": "the behavior succeeds and returns a valid, documented result",
                "verification": "automated test and smoke check",
                "status": "draft",
            }
        )
    for requirement in non_functional_requirements:
        index = len(criteria) + 1
        criteria.append(
            {
                "id": f"AC-{index:03d}",
                "requirement": requirement,
                "given": "the generated application is built and tested",
                "when": f"the {requirement} quality is evaluated",
                "then": f"the implementation demonstrates the requested {requirement} quality",
                "verification": "quality gate evidence",
                "status": "draft",
            }
        )
    return criteria


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
        domain_entities=_extract_domain_entities(raw_request, functional_requirements),
        acceptance_criteria=_build_acceptance_criteria(
            functional_requirements, non_functional_requirements
        ),
        acceptance_approval={"status": "pending"},
        constraints=_extract_constraints(raw_request),
        assumptions=_build_assumptions(raw_request),
        # Automatic clarification questions are intentionally disabled. The
        # generic questions did not add enough context to improve generation.
        open_questions=[],
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
        "## Domain Entities",
        *_render_bullets(list(requirements.get("domain_entities", []))),
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
                list(requirements.get("functional_requirements", []))
            )
        ),
        "",
        "## Acceptance Criteria",
        *[
            f"- **{criterion['id']}**: {criterion['requirement']}"
            for criterion in requirements.get("acceptance_criteria", [])
        ],
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
        "open_questions_markdown": str(prd_path)
        if requirements.get("open_questions")
        else "",
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
    requirements = build_requirement_artifact(
        raw_request, project_name, state.get("input_type")
    )
    model_analysis, observability, warning = _model_requirement_analysis(
        raw_request, state
    )
    if model_analysis:
        functional = model_analysis["functional_requirements"]
        non_functional = model_analysis["non_functional_requirements"]
        requirements.update(model_analysis)
        requirements["acceptance_criteria"] = _build_acceptance_criteria(
            functional, non_functional
        )
        requirements["complexity"] = classify_complexity(raw_request, functional)
    if observability:
        requirements["observability"] = observability
    if warning:
        requirements["analysis_warning"] = warning
    requirements["created_at"] = state.get("timestamp", "")
    artifact_paths = persist_requirement_artifacts(
        requirements, artifact_manifest, state["job_id"]
    )

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
        persist_job_checkpoint(
            {**state, **updates}, artifact_manifest, suffix="requirement_analysis"
        )
    )
    return updates


def render_acceptance_criteria_markdown(requirements: RequirementArtifact) -> str:
    """Render the approved, stable acceptance baseline used by later gates."""
    approval = requirements.get("acceptance_approval", {})
    lines = [
        "# Approved Acceptance Criteria",
        "",
        f"**Status**: {approval.get('status', 'pending')}",
        f"**Approved By**: {approval.get('approved_by', 'not approved')}",
        f"**Approved At**: {approval.get('approved_at', '')}",
        "",
    ]
    for criterion in requirements.get("acceptance_criteria", []):
        lines.extend(
            [
                f"## {criterion['id']}: {criterion['requirement']}",
                "",
                f"- Given: {criterion['given']}",
                f"- When: {criterion['when']}",
                f"- Then: {criterion['then']}",
                f"- Verification: {criterion['verification']}",
                f"- Status: {criterion['status']}",
                "",
            ]
        )
    return "\n".join(lines)


def approve_acceptance_criteria(state: BuilderState) -> Dict[str, Any]:
    """Approve the submitted requirement baseline without asking generic questions."""
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".", project_name=state.get("project_name")
    )
    requirements = dict(state.get("requirements") or {})
    approved_at = datetime.now(timezone.utc).isoformat()
    requirements["acceptance_criteria"] = [
        {**criterion, "status": "approved"}
        for criterion in requirements.get("acceptance_criteria", [])
    ]
    requirements["acceptance_approval"] = {
        "status": "approved",
        "approved_by": "submitted request",
        "approved_at": approved_at,
        "basis": "The user-submitted request is the generation baseline; no extra features were inferred.",
    }
    requirements_dir = Path(manifest["requirements_dir"])
    requirements_dir.mkdir(parents=True, exist_ok=True)
    acceptance_path = requirements_dir / "acceptance-criteria.md"
    acceptance_path.write_text(
        render_acceptance_criteria_markdown(requirements), encoding="utf-8"
    )
    artifact_paths = dict(requirements.get("artifact_paths") or {})
    artifact_paths["acceptance_criteria_markdown"] = str(acceptance_path)
    requirements["artifact_paths"] = artifact_paths
    updates = {
        "requirements": requirements,
        "current_phase": "acceptance_approval",
        "job_status": "running",
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint(
            {**state, **updates}, manifest, suffix="acceptance_approval"
        )
    )
    return updates
