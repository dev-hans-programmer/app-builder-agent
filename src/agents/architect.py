"""
Architecture planning agent.

This module turns normalized requirements into a structured architecture
artifact that can drive spec decomposition and implementation planning.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from src.graph.runtime import (
    ArchitectureArtifact,
    ensure_workspace_layout,
    persist_job_checkpoint,
)
from src.graph.state import BuilderState


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "api",
    "app",
    "application",
    "build",
    "backend",
    "create",
    "for",
    "in",
    "of",
    "or",
    "operations",
    "service",
    "system",
    "the",
    "to",
    "use",
    "with",
}


def _requirements_to_text(requirements: Dict[str, Any]) -> str:
    clarification_answers = requirements.get("clarification_answers", []) or []
    clarification_text = " ".join(
        f"{item.get('question', '')} {item.get('answer', '')}"
        for item in clarification_answers
    )
    parts = [
        str(requirements.get("summary", "")),
        " ".join(requirements.get("functional_requirements", []) or []),
        " ".join(requirements.get("non_functional_requirements", []) or []),
        " ".join(requirements.get("constraints", []) or []),
        clarification_text,
    ]
    return " ".join(part for part in parts if part).lower()


def _infer_primary_entities(requirements_text: str) -> list[str]:
    entities: list[str] = []
    patterns = [
        r"\b(?:build|create|manage|track|handle|support|assign|link|store)\s+(?:a|an|the)?\s*([a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*){0,2})",
        r"\bfor\s+(?:a|an|the)?\s*([a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*){0,2})",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, requirements_text):
            candidate = " ".join(
                token for token in match.split() if token not in _STOP_WORDS
            ).strip()
            if candidate and candidate not in entities:
                entities.append(candidate)
    if not entities:
        fallback_words = [
            word
            for word in re.findall(r"[a-z][a-z0-9_-]*", requirements_text)
            if word not in _STOP_WORDS
            and word
            not in {
                "crud",
                "secure",
                "simple",
                "specific",
                "implementation",
                "stack",
                "mentioned",
            }
        ]
        entities.append(
            fallback_words[0].replace("-app", "") if fallback_words else "core resource"
        )
    return entities


def _build_relationships(entities: list[str]) -> list[str]:
    relationships = [
        "Treat API resources as application-owned domain objects.",
        "Keep request DTOs separate from persistence records.",
    ]
    if len(entities) >= 2:
        relationships.append(
            f"Model the relationship between {entities[0]} and {entities[1]} explicitly."
        )
    if len(entities) >= 3:
        relationships.append(
            f"Extend the model to capture how {entities[2]} relates to the primary flow."
        )
    return relationships


def _build_layers(requirements_text: str, entities: list[str]) -> list[str]:
    layers: list[str] = []
    if entities or any(
        token in requirements_text for token in ("api", "endpoint", "route", "http")
    ):
        layers.append("transport")
    if entities or any(
        token in requirements_text
        for token in (
            "workflow",
            "process",
            "manage",
            "create",
            "update",
            "support",
            "handle",
        )
    ):
        layers.append("application")
    if entities:
        layers.append("domain")
    if any(
        token in requirements_text
        for token in ("database", "persistence", "persist", "storage")
    ):
        layers.append("data")
    if any(
        token in requirements_text
        for token in ("queue", "worker", "external", "integration", "service")
    ):
        layers.append("infrastructure")
    if any(
        token in requirements_text
        for token in ("auth", "login", "oauth", "role", "permission", "authorization")
    ):
        layers.append("security")
    if any(
        token in requirements_text
        for token in ("observability", "logging", "monitor", "metrics", "tracing")
    ):
        layers.append("observability")
    if any(
        token in requirements_text
        for token in ("config", "configuration", "env", "environment", "secret")
    ):
        layers.append("configuration")
    if not layers:
        layers.append("application")
    return layers


def _build_module_map(
    requirements_text: str, entities: list[str]
) -> Dict[str, list[str]]:
    module_map: Dict[str, list[str]] = {}
    if entities or any(
        token in requirements_text for token in ("api", "endpoint", "route", "http")
    ):
        module_map["transport"] = [
            "routes",
            "request validation",
            "response serialization",
        ]
    if entities or any(
        token in requirements_text
        for token in (
            "workflow",
            "process",
            "manage",
            "create",
            "update",
            "support",
            "handle",
        )
    ):
        module_map["application"] = [
            "use cases",
            "orchestration",
            "service coordination",
        ]
    if entities:
        module_map["domain"] = ["entities", "value objects", "business rules"]
    if any(
        token in requirements_text
        for token in ("database", "persistence", "persist", "storage")
    ):
        module_map["data"] = ["repositories", "migrations", "schemas"]
    if any(
        token in requirements_text
        for token in ("queue", "worker", "external", "integration", "service")
    ):
        module_map["infrastructure"] = [
            "adapters",
            "integration clients",
            "background jobs",
        ]
    if any(
        token in requirements_text
        for token in ("auth", "login", "oauth", "role", "permission", "authorization")
    ):
        module_map["security"] = [
            "authentication",
            "authorization",
            "session or token handling",
        ]
    if any(
        token in requirements_text
        for token in ("observability", "logging", "monitor", "metrics", "tracing")
    ):
        module_map["observability"] = ["logging", "metrics", "tracing"]
    if any(
        token in requirements_text
        for token in ("config", "configuration", "env", "environment", "secret")
    ):
        module_map["configuration"] = ["settings", "environment loading", "bootstrap"]
    if not module_map:
        module_map["application"] = ["requirement-driven orchestration"]
    return module_map


def _build_service_boundaries(requirements_text: str, entities: list[str]) -> list[str]:
    boundaries: list[str] = []
    if len(entities) >= 2:
        boundaries.append(
            f"Keep {entities[0]} handling separate from {entities[1]} handling."
        )
    if any(token in requirements_text for token in ("queue", "worker", "background")):
        boundaries.append("Move background processing into a separate boundary.")
    if any(
        token in requirements_text for token in ("websocket", "real-time", "realtime")
    ):
        boundaries.append(
            "Separate real-time transport concerns from request/response flows."
        )
    return boundaries


def _build_data_model(
    requirements_text: str, entities: list[str] | None = None
) -> list[str]:
    entities = entities or _infer_primary_entities(requirements_text)
    model = [f"Primary entities: {', '.join(entities)}."]
    if any(
        token in requirements_text
        for token in ("database", "persistence", "persist", "storage")
    ):
        model.append("Persist domain state through storage-backed models.")
    model.extend(_build_relationships(entities))
    return model


def _build_api_contracts(
    requirements_text: str, entities: list[str] | None = None
) -> list[str]:
    entities = entities or _infer_primary_entities(requirements_text)
    contracts: list[str] = []
    for entity in entities[:3]:
        contracts.append(f"Provide only the approved operations for {entity}.")
    if len(entities) >= 2:
        contracts.append(
            f"Provide endpoints that manage the relationship between {entities[0]} and {entities[1]}."
        )
    if any(
        token in requirements_text
        for token in ("auth", "login", "oauth", "role", "permission", "authorization")
    ):
        contracts.append(
            "Expose authentication endpoints and protect state-changing routes."
        )
    if "search" in requirements_text:
        contracts.append("Provide search and filtering endpoints for discoverability.")
    if not contracts:
        contracts.append("Derive the API surface directly from the requirement text.")
    return contracts


def _contract_name(entity: str) -> str:
    words = re.findall(r"[a-z0-9]+", entity.lower()) or ["resource"]
    return "".join(word.capitalize() for word in words)


def _contract_path(entity: str) -> str:
    words = re.findall(r"[a-z0-9]+", entity.lower()) or ["resources"]
    name = "-".join(words)
    return name if name.endswith("s") else f"{name}s"


def _criterion_ids(criteria: list[Dict[str, Any]], terms: tuple[str, ...]) -> list[str]:
    matched = [
        str(item["id"])
        for item in criteria
        if item.get("id")
        and any(term in str(item.get("requirement", "")).lower() for term in terms)
    ]
    return matched or [str(item["id"]) for item in criteria if item.get("id")]


def _production_entities(
    requirements_text: str, explicit_entities: list[str] | None = None
) -> list[str]:
    entities = [
        str(entity).strip().lower()
        for entity in (explicit_entities or _infer_primary_entities(requirements_text))
        if str(entity).strip().lower()
        not in {
            "complete",
            "completed",
            "completion",
            "login",
            "pagination",
            "priority",
            "search",
        }
    ]
    if _needs_rbac(requirements_text) and "user" not in entities:
        entities.insert(0, "user")
    return list(dict.fromkeys(entities or ["core resource"]))


def _build_structured_api_contracts(
    entities: list[str], criteria: list[Dict[str, Any]], requirements_text: str
) -> list[Dict[str, Any]]:
    """Create explicit endpoint contracts generation and tests can share."""
    contracts: list[Dict[str, Any]] = []
    api_prefix = "/api/v1"
    if _needs_rbac(requirements_text):
        auth_operations = [
            (
                "POST",
                "/auth/register",
                "register user",
                "UserRegistrationRequest",
                "UserProfileResponse",
                201,
                ("register", "registration", "sign up"),
            ),
            (
                "POST",
                "/auth/login",
                "login user",
                "UserLoginRequest",
                "TokenResponse",
                200,
                ("login", "authentication", "authenticate"),
            ),
        ]
        if any(
            marker in requirements_text
            for marker in ("profile", "current user", "user details")
        ):
            auth_operations.append(
                (
                    "GET",
                    "/users/me",
                    "get current user profile",
                    "none",
                    "UserProfileResponse",
                    200,
                    ("profile", "current user"),
                )
            )
        for (
            method,
            path,
            operation,
            request,
            response,
            status,
            terms,
        ) in auth_operations:
            contracts.append(
                {
                    "id": f"API-{len(contracts) + 1:03d}",
                    "method": method,
                    "path": f"{api_prefix}{path}",
                    "operation": operation,
                    "request_schema": request,
                    "response_schema": response,
                    "success_status": status,
                    "error_statuses": [400, 401, 409, 422, 500],
                    "acceptance_criteria_ids": _criterion_ids(criteria, terms),
                }
            )
    all_operations = (
        ("POST", "", "create", 201),
        ("GET", "", "list", 200),
        ("GET", "/{id}", "get", 200),
        ("PATCH", "/{id}", "update", 200),
        ("DELETE", "/{id}", "delete", 204),
    )
    if any(
        marker in requirements_text
        for marker in ("crud", "manage", "lifecycle", "todo", "task")
    ):
        operations = all_operations
    else:
        operations = tuple(
            operation
            for operation in all_operations
            if (
                operation[2] == "create"
                and any(marker in requirements_text for marker in ("create", "add"))
                or operation[2] == "list"
                and any(
                    marker in requirements_text
                    for marker in ("list", "search", "browse")
                )
                or operation[2] == "get"
                and any(
                    marker in requirements_text
                    for marker in ("get", "read", "view", "fetch")
                )
                or operation[2] == "update"
                and any(marker in requirements_text for marker in ("update", "edit"))
                or operation[2] == "delete"
                and any(marker in requirements_text for marker in ("delete", "remove"))
            )
        )
        if not operations:
            operations = tuple(
                operation
                for operation in all_operations
                if operation[2] in {"list", "get"}
            )
    operation_terms = {
        "create": ("create", "add"),
        "list": ("list", "search", "filter", "sort", "paginate", "view"),
        "get": ("view", "get", "read"),
        "update": ("update", "edit", "complete", "incomplete"),
        "delete": ("delete", "remove"),
    }
    resource_entities = [entity for entity in entities if entity != "user"]
    for entity in resource_entities[:3]:
        schema = _contract_name(entity)
        resource_path = _contract_path(entity)
        for method, suffix, operation, success_status in operations:
            contract_id = f"API-{len(contracts) + 1:03d}"
            contracts.append(
                {
                    "id": contract_id,
                    "method": method,
                    "path": f"{api_prefix}/{resource_path}{suffix}",
                    "operation": f"{operation} {entity}",
                    "request_schema": (
                        f"{schema}Create"
                        if operation == "create"
                        else f"{schema}Update"
                        if operation == "update"
                        else "none"
                    ),
                    "response_schema": (
                        "none"
                        if operation == "delete"
                        else f"list[{schema}]"
                        if operation == "list"
                        else schema
                    ),
                    "success_status": success_status,
                    "error_statuses": [400, 404, 422, 500],
                    "acceptance_criteria_ids": _criterion_ids(
                        criteria, operation_terms[operation]
                    ),
                }
            )
    return contracts


def _build_data_contracts(
    entities: list[str], criteria: list[Dict[str, Any]]
) -> list[Dict[str, Any]]:
    """Create a conservative data shape without inventing product features."""
    contracts: list[Dict[str, Any]] = []
    for index, entity in enumerate(entities[:3], start=1):
        normalized = entity.lower()
        fields = [
            {"name": "id", "type": "uuid", "required": True, "immutable": True},
            {
                "name": "created_at",
                "type": "datetime",
                "required": True,
                "immutable": True,
            },
            {
                "name": "updated_at",
                "type": "datetime",
                "required": True,
                "immutable": False,
            },
        ]
        if normalized == "user":
            fields[1:1] = [
                {
                    "name": "email",
                    "type": "email",
                    "required": True,
                    "immutable": False,
                },
                {
                    "name": "password_hash",
                    "type": "string",
                    "required": True,
                    "immutable": False,
                },
            ]
            terms = ("user", "registration", "login", "profile", "authentication")
        elif "todo" in normalized or "task" in normalized:
            fields[1:1] = [
                {
                    "name": "owner_id",
                    "type": "uuid",
                    "required": True,
                    "immutable": True,
                },
                {
                    "name": "title",
                    "type": "string",
                    "required": True,
                    "immutable": False,
                },
                {
                    "name": "description",
                    "type": "string|null",
                    "required": False,
                    "immutable": False,
                },
                {
                    "name": "priority",
                    "type": "low|medium|high",
                    "required": True,
                    "immutable": False,
                },
                {
                    "name": "due_date",
                    "type": "date|null",
                    "required": False,
                    "immutable": False,
                },
                {
                    "name": "completed",
                    "type": "boolean",
                    "required": True,
                    "immutable": False,
                },
            ]
            terms = ("todo", "task", "priority", "due date", "completed")
        else:
            fields.insert(
                1,
                {
                    "name": "name",
                    "type": "string",
                    "required": True,
                    "immutable": False,
                },
            )
            terms = (normalized,)
        contracts.append(
            {
                "id": f"DATA-{index:03d}",
                "entity": _contract_name(entity),
                "fields": fields,
                "acceptance_criteria_ids": _criterion_ids(criteria, terms),
            }
        )
    return contracts


def _build_error_contract() -> Dict[str, Any]:
    return {
        "id": "ERROR-001",
        "content_type": "application/json",
        "fields": ["error.code", "error.message", "error.details", "request_id"],
        "rule": "Errors use a stable machine code and never expose stack traces to clients.",
    }


def _needs_rbac(requirements_text: str) -> bool:
    return any(
        marker in requirements_text
        for marker in (
            "auth",
            "login",
            "permission",
            "permissions",
            "role",
            "roles",
            "access control",
            "authorization",
            "owner",
            "admin",
            "administrator",
            "member",
            "membership",
        )
    )


def _build_rbac_model(requirements_text: str) -> list[str]:
    if not _needs_rbac(requirements_text):
        return []
    rbac = [
        "Treat access checks as scoped to the current domain context.",
        "Resolve permissions from the user's relationship to the active resource set.",
    ]
    if "owner" in requirements_text:
        rbac.append(
            "The owning actor receives full administrative permissions by default."
        )
    if "admin" in requirements_text or "administrator" in requirements_text:
        rbac.append("Administrators can manage elevated actions inside the domain.")
    if "member" in requirements_text:
        rbac.append(
            "Members receive constrained access aligned with their assigned role."
        )
    return rbac


def _build_lifecycle(
    requirements_text: str, entities: list[str] | None = None
) -> list[str]:
    lifecycle: list[str] = []
    entities = entities or _infer_primary_entities(requirements_text)
    if entities:
        lifecycle.append(
            f"Capture the lifecycle for {entities[0]} from request to response."
        )
    if any(
        token in requirements_text
        for token in ("validate", "validation", "check", "verify")
    ):
        lifecycle.append("Validate inputs before business rules mutate state.")
    if any(
        token in requirements_text
        for token in ("respond", "response", "return", "output")
    ):
        lifecycle.append(
            "Emit a clear completion response after each state transition."
        )
    if any(token in requirements_text for token in ("auth", "login")):
        lifecycle.append(
            "Require authenticated context before protected lifecycle steps."
        )
    if not lifecycle:
        lifecycle.append("Derive lifecycle steps directly from the PRD.")
    return lifecycle


def _build_security_strategy(requirements_text: str) -> list[str]:
    strategy: list[str] = []
    if any(
        token in requirements_text
        for token in ("auth", "login", "oauth", "role", "permission", "authorization")
    ):
        strategy.append(
            "Add identity and access control with explicit authentication flows."
        )
    if any(
        token in requirements_text
        for token in ("secret", "secrets", "credential", "credentials")
    ):
        strategy.append("Manage secrets externally instead of embedding them in code.")
    if any(
        token in requirements_text
        for token in ("validate", "validation", "input", "payload")
    ):
        strategy.append("Validate request payloads at the boundary.")
    return strategy


def _build_configuration_strategy(requirements_text: str) -> list[str]:
    strategy: list[str] = []
    if any(
        token in requirements_text
        for token in ("env", "environment", "config", "configuration", "settings")
    ):
        strategy.append(
            "Load runtime settings through a dedicated configuration layer."
        )
    if any(
        token in requirements_text
        for token in ("database", "persistence", "persist", "storage")
    ):
        strategy.append(
            "Store connection or storage settings in the configuration layer."
        )
    if any(
        token in requirements_text for token in ("queue", "worker", "retry", "timeout")
    ):
        strategy.append("Add execution settings for background processing.")
    return strategy


def _build_observability_strategy(requirements_text: str) -> list[str]:
    strategy: list[str] = []
    if any(
        token in requirements_text
        for token in ("observability", "logging", "monitor", "metrics", "tracing")
    ):
        strategy.append(
            "Add structured logging and traceability around the relevant flow."
        )
    if any(token in requirements_text for token in ("metrics", "monitor", "tracing")):
        strategy.append(
            "Include metrics or tracing where the requirement calls for visibility."
        )
    return strategy


def _build_deployment_notes(requirements_text: str) -> list[str]:
    notes: list[str] = []
    if any(
        token in requirements_text
        for token in ("deploy", "deployment", "host", "hosting", "production")
    ):
        notes.append(
            "Shape the runtime and packaging around the stated deployment target."
        )
    if any(
        token in requirements_text for token in ("websocket", "real-time", "realtime")
    ):
        notes.append("Ensure the deployment path supports long-lived connections.")
    return notes


def _build_decisions(requirements_text: str, entities: list[str]) -> list[str]:
    decisions: list[str] = []
    if entities:
        decisions.append(f"Center implementation around {', '.join(entities)}.")
    if any(
        token in requirements_text
        for token in ("database", "persistence", "persist", "storage")
    ):
        decisions.append("Isolate storage concerns from the core domain flow.")
    if any(
        token in requirements_text
        for token in ("auth", "login", "oauth", "role", "permission", "authorization")
    ):
        decisions.append("Treat access control as a dedicated concern.")
    if not decisions:
        decisions.append(
            "Use the extracted requirement structure to guide implementation order."
        )
    return decisions


def _build_verification_strategy(
    requirements_text: str, entities: list[str]
) -> list[str]:
    strategy: list[str] = []
    if entities:
        strategy.append(
            f"Verify the lifecycle and shape of {entities[0]} against the PRD."
        )
    if (
        "link" in requirements_text
        or "associate" in requirements_text
        or "relationship" in requirements_text
    ):
        strategy.append("Add relationship checks to the verification matrix.")
    if any(
        token in requirements_text
        for token in ("auth", "login", "oauth", "role", "permission", "authorization")
    ):
        strategy.append("Verify authentication and authorization flows explicitly.")
    if any(
        token in requirements_text
        for token in ("database", "persistence", "persist", "storage")
    ):
        strategy.append("Verify storage behavior against the documented requirement.")
    return strategy


def _build_risks(requirements_text: str) -> list[str]:
    risks: list[str] = []
    if (
        "database" not in requirements_text
        and "persistence" not in requirements_text
        and "persist" not in requirements_text
        and "storage" not in requirements_text
    ):
        risks.append(
            "Storage expectations remain open if the requirement did not specify a persistence model."
        )
    if (
        "auth" not in requirements_text
        and "login" not in requirements_text
        and "oauth" not in requirements_text
        and "role" not in requirements_text
    ):
        risks.append(
            "Access control may still need clarification if the requirement introduces protected actions later."
        )
    return risks


def _build_python_production_architecture(
    policy: Dict[str, Any], requirements_text: str
) -> Dict[str, Any]:
    """Compile binding policy decisions into a generation blueprint."""
    if not policy.get("enabled"):
        return {}
    conditional: list[Dict[str, str]] = []
    for component, markers in {
        "redis": ("cache", "distributed lock", "rate limit"),
        "background_worker": ("queue", "worker", "background job", "scheduled"),
        "external_client": ("external api", "third-party", "integration"),
    }.items():
        required = any(marker in requirements_text for marker in markers)
        conditional.append(
            {
                "component": component,
                "decision": "include" if required else "omit",
                "reason": (
                    "Explicit requirement detected."
                    if required
                    else "No requirement justifies this infrastructure."
                ),
            }
        )
    return {
        "policy_id": policy.get("id"),
        "policy_version": policy.get("version"),
        "policy_sha256": policy.get("sha256"),
        "runtime": "Python 3.13+ / FastAPI / Pydantic v2",
        "database": "PostgreSQL with SQLAlchemy 2.x async sessions and Alembic migrations",
        "architecture_style": "modular monolith with clean dependency boundaries",
        "project_structure": [
            "app/api/routes",
            "app/api/dependencies",
            "app/core",
            "app/domain/entities",
            "app/domain/errors",
            "app/domain/value_objects",
            "app/application/use_cases",
            "app/application/dto",
            "app/infrastructure/database",
            "app/infrastructure/repositories",
            "app/schemas/requests",
            "app/schemas/responses",
            "app/middleware",
            "tests/unit",
            "tests/integration",
            "tests/api",
            "alembic/versions",
            ".github/workflows",
        ],
        "dependency_rules": [
            "Domain imports no FastAPI, SQLAlchemy, or infrastructure modules.",
            "Application imports domain abstractions, never FastAPI HTTPException.",
            "Infrastructure implements application/domain ports and contains persistence details.",
            "API routes are thin and translate application errors only through centralized handlers.",
            "Database ORM models are never returned directly as API schemas.",
        ],
        "mandatory_deliverables": [
            "pyproject.toml and uv.lock",
            "typed Pydantic Settings and .env.example",
            "central application error hierarchy and HTTP error mapping",
            "structured JSON logging and request IDs",
            "OpenTelemetry tracing and Prometheus-compatible metrics",
            "liveness and dependency-aware readiness endpoints",
            "versioned /api/v1 routes",
            "SQLAlchemy models, repositories, and Alembic migration",
            "unit, integration, API, authentication, authorization, and error tests",
            "non-root production Dockerfile and local Docker Compose",
            "Ruff, mypy, pytest, pre-commit, Makefile, and GitHub Actions",
            "architecture and operations documentation",
        ],
        "conditional_components": conditional,
    }


def render_production_architecture_markdown(architecture: ArchitectureArtifact) -> str:
    blueprint = architecture.get("python_production", {})
    if not blueprint:
        return "# Python Production Architecture\n\nNot applicable to this stack.\n"
    lines = [
        "# Python Production Architecture",
        "",
        f"- Policy: `{blueprint.get('policy_id')}`",
        f"- Version: `{blueprint.get('policy_version')}`",
        f"- SHA-256: `{blueprint.get('policy_sha256')}`",
        f"- Runtime: {blueprint.get('runtime')}",
        f"- Database: {blueprint.get('database')}",
        f"- Style: {blueprint.get('architecture_style')}",
        "",
        "## Required Project Structure",
        *[f"- `{item}`" for item in blueprint.get("project_structure", [])],
        "",
        "## Dependency Rules",
        *[f"- {item}" for item in blueprint.get("dependency_rules", [])],
        "",
        "## Mandatory Deliverables",
        *[f"- {item}" for item in blueprint.get("mandatory_deliverables", [])],
        "",
        "## Conditional Infrastructure Decisions",
    ]
    for decision in blueprint.get("conditional_components", []):
        lines.append(
            f"- **{decision['component']}**: {decision['decision']} — {decision['reason']}"
        )
    lines.append("")
    return "\n".join(lines)


def build_architecture_artifact(
    requirements: Dict[str, Any],
    project_name: str,
    backend_policy: Dict[str, Any] | None = None,
) -> ArchitectureArtifact:
    """Build a structured architecture artifact from requirement metadata."""
    requirements_text = _requirements_to_text(requirements)
    entities = _production_entities(
        requirements_text,
        [str(item) for item in requirements.get("domain_entities", [])],
    )
    criteria = list(requirements.get("acceptance_criteria", []))
    summary = (
        requirements.get("summary")
        or requirements.get("title")
        or f"Architecture for {project_name}"
    )

    return ArchitectureArtifact(
        id=f"{project_name}-architecture",
        title=f"Architecture for {project_name}",
        source_requirement_id=str(
            requirements.get("id", f"{project_name}-requirements")
        ),
        summary=summary,
        layers=_build_layers(requirements_text, entities),
        module_map=_build_module_map(requirements_text, entities),
        service_boundaries=_build_service_boundaries(requirements_text, entities),
        data_model=_build_data_model(requirements_text, entities),
        api_surface=_build_api_contracts(requirements_text, entities),
        api_contracts=_build_structured_api_contracts(
            entities, criteria, requirements_text
        ),
        data_contracts=_build_data_contracts(entities, criteria),
        error_contract=_build_error_contract(),
        security_strategy=_build_security_strategy(requirements_text),
        configuration_strategy=_build_configuration_strategy(requirements_text),
        observability_strategy=_build_observability_strategy(requirements_text),
        deployment_notes=_build_deployment_notes(requirements_text),
        decisions=_build_decisions(requirements_text, entities),
        risks=_build_risks(requirements_text),
        primary_entities=entities,
        rbac_model=_build_rbac_model(requirements_text),
        lifecycle=_build_lifecycle(requirements_text, entities),
        verification_strategy=_build_verification_strategy(requirements_text, entities),
        complexity=str(requirements.get("complexity", "simple")),
        created_at="",
        python_production=_build_python_production_architecture(
            backend_policy or {}, requirements_text
        ),
    )


def render_architecture_markdown(architecture: ArchitectureArtifact) -> str:
    """Render the architecture artifact as markdown."""
    module_map = architecture.get("module_map", {})
    module_lines = []
    for module_name, concerns in module_map.items():
        module_lines.append(f"### {module_name}")
        module_lines.extend(f"- {concern}" for concern in concerns)
        module_lines.append("")

    api_contracts = list(architecture.get("api_surface", []))
    data_model = list(architecture.get("data_model", []))
    lifecycle = list(architecture.get("lifecycle", []))
    rbac_model = list(architecture.get("rbac_model", []))
    verification_strategy = list(architecture.get("verification_strategy", []))
    primary_entities = list(architecture.get("primary_entities", []))

    sections = [
        "# Technical Design",
        "",
        f"**ID**: {architecture['id']}",
        f"**Title**: {architecture['title']}",
        f"**Requirement Source**: {architecture['source_requirement_id']}",
        f"**Complexity**: {architecture['complexity']}",
        "",
        "## Summary",
        architecture["summary"],
        "",
        "## Domain Model",
        *[f"- {item}" for item in data_model],
        "",
        "## Primary Entities",
        *[f"- {item}" for item in primary_entities],
        "",
        "## Layers",
        *[f"- {layer}" for layer in architecture.get("layers", [])],
        "",
        "## Module Map",
        *module_lines,
        "## Service Boundaries",
        *[f"- {item}" for item in architecture.get("service_boundaries", [])],
        "",
        "## API Surface",
        *[f"- {item}" for item in api_contracts],
        "",
        "## RBAC Model",
        *[f"- {item}" for item in rbac_model],
        "",
        "## Lifecycle",
        *[f"- {item}" for item in lifecycle],
        "",
        "## Security Strategy",
        *[f"- {item}" for item in architecture.get("security_strategy", [])],
        "",
        "## Configuration Strategy",
        *[f"- {item}" for item in architecture.get("configuration_strategy", [])],
        "",
        "## Observability Strategy",
        *[f"- {item}" for item in architecture.get("observability_strategy", [])],
        "",
        "## Deployment Notes",
        *[f"- {item}" for item in architecture.get("deployment_notes", [])],
        "",
        "## Verification Strategy",
        *[f"- {item}" for item in verification_strategy],
        "",
        "## Decisions",
        *[f"- {item}" for item in architecture.get("decisions", [])],
        "",
        "## Risks",
        *[f"- {item}" for item in architecture.get("risks", [])],
        "",
    ]
    return "\n".join(sections)


def render_api_contracts_markdown(architecture: ArchitectureArtifact) -> str:
    lines = ["# API Contracts", ""]
    for contract in architecture.get("api_contracts", []):
        lines.extend(
            [
                f"## {contract['id']}: {contract['method']} {contract['path']}",
                "",
                f"- Operation: {contract['operation']}",
                f"- Request: `{contract['request_schema']}`",
                f"- Response: `{contract['response_schema']}`",
                f"- Success status: `{contract['success_status']}`",
                f"- Error statuses: {', '.join(str(code) for code in contract['error_statuses'])}",
                f"- Acceptance criteria: {', '.join(contract['acceptance_criteria_ids']) or 'none'}",
                "",
            ]
        )
    error = architecture.get("error_contract", {})
    lines.extend(
        [
            "## Shared Error Contract",
            "",
            f"- ID: {error.get('id', '')}",
            f"- Content type: `{error.get('content_type', '')}`",
            f"- Fields: {', '.join(error.get('fields', []))}",
            f"- Rule: {error.get('rule', '')}",
            "",
        ]
    )
    return "\n".join(lines)


def render_data_contracts_markdown(architecture: ArchitectureArtifact) -> str:
    lines = ["# Data Contracts", ""]
    for contract in architecture.get("data_contracts", []):
        lines.extend([f"## {contract['id']}: {contract['entity']}", ""])
        for field in contract.get("fields", []):
            lines.append(
                f"- `{field['name']}: {field['type']}` — "
                f"required={str(field['required']).lower()}, immutable={str(field['immutable']).lower()}"
            )
        lines.extend(
            [
                f"- Acceptance criteria: {', '.join(contract['acceptance_criteria_ids']) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines)


def persist_architecture_artifacts(
    architecture: ArchitectureArtifact,
    manifest: Dict[str, str],
    job_id: str,
) -> Dict[str, str]:
    """Persist the technical design as a single markdown file."""
    architecture_dir = Path(manifest["architecture_dir"])
    architecture_dir.mkdir(parents=True, exist_ok=True)

    md_path = architecture_dir / "technical-design.md"
    md_path.write_text(render_architecture_markdown(architecture), encoding="utf-8")
    api_path = architecture_dir / "api-contracts.md"
    api_path.write_text(render_api_contracts_markdown(architecture), encoding="utf-8")
    data_path = architecture_dir / "data-contracts.md"
    data_path.write_text(render_data_contracts_markdown(architecture), encoding="utf-8")
    production_path = architecture_dir / "python-production-architecture.md"
    production_path.write_text(
        render_production_architecture_markdown(architecture), encoding="utf-8"
    )

    return {
        "technical_design_markdown": str(md_path),
        "architecture_markdown": str(md_path),
        "architecture_json": str(md_path),
        "decision_log_markdown": str(md_path),
        "module_map_json": str(md_path),
        "api_contracts_markdown": str(api_path),
        "data_contracts_markdown": str(data_path),
        "python_production_architecture_markdown": str(production_path),
    }


def validate_architecture_consistency(
    requirements: Dict[str, Any],
    architecture: ArchitectureArtifact,
) -> list[str]:
    """Validate that architecture reflects the requirement intent."""
    errors: list[str] = []
    requirement_text = _requirements_to_text(requirements)

    if "database" in requirement_text and "data" not in architecture.get(
        "module_map", {}
    ):
        errors.append(
            "Architecture should include a data module when persistence is required."
        )
    if (
        "auth" in requirement_text
        or "login" in requirement_text
        or "oauth" in requirement_text
    ) and "security" not in architecture.get("module_map", {}):
        errors.append(
            "Architecture should include a security module when auth is required."
        )
    if not architecture.get("layers"):
        errors.append("Architecture must define at least one layer.")
    if not architecture.get("decisions"):
        errors.append("Architecture must include decision notes.")
    if not architecture.get("primary_entities"):
        errors.append(
            "Architecture must infer at least one primary entity from the requirement."
        )

    return errors


def analyze_architecture(state: BuilderState) -> Dict[str, Any]:
    """Analyze normalized requirements and persist the architecture artifact."""
    requirements = state.get("requirements") or {}
    project_name = state["project_name"]
    artifact_manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    backend_policy = state.get("backend_policy") or {}
    architecture = build_architecture_artifact(
        requirements, project_name, backend_policy
    )
    architecture["created_at"] = state.get("timestamp", "")
    requirements_text = _requirements_to_text(requirements)
    entities = _production_entities(requirements_text)
    architecture["layers"] = _build_layers(requirements_text, entities)
    architecture["module_map"] = _build_module_map(requirements_text, entities)
    architecture["api_surface"] = _build_api_contracts(requirements_text)
    criteria = list(requirements.get("acceptance_criteria", []))
    architecture["api_contracts"] = _build_structured_api_contracts(
        entities, criteria, requirements_text
    )
    architecture["data_contracts"] = _build_data_contracts(entities, criteria)
    architecture["error_contract"] = _build_error_contract()
    architecture["data_model"] = _build_data_model(requirements_text)
    architecture["service_boundaries"] = _build_service_boundaries(
        requirements_text, entities
    )
    architecture["security_strategy"] = _build_security_strategy(requirements_text)
    architecture["configuration_strategy"] = _build_configuration_strategy(
        requirements_text
    )
    architecture["observability_strategy"] = _build_observability_strategy(
        requirements_text
    )
    architecture["deployment_notes"] = _build_deployment_notes(requirements_text)
    architecture["decisions"] = _build_decisions(requirements_text, entities)
    architecture["risks"] = _build_risks(requirements_text)
    architecture["primary_entities"] = entities
    architecture["lifecycle"] = _build_lifecycle(requirements_text)
    architecture["rbac_model"] = _build_rbac_model(requirements_text)
    architecture["verification_strategy"] = _build_verification_strategy(
        requirements_text, entities
    )
    consistency_errors = validate_architecture_consistency(requirements, architecture)
    artifact_paths = persist_architecture_artifacts(
        architecture, artifact_manifest, state["job_id"]
    )

    updates = {
        "architecture_plan": {
            **architecture,
            "artifact_paths": artifact_paths,
            "consistency_errors": consistency_errors,
        },
        "job_status": "running",
        "current_phase": "architecture_planning",
        "artifacts": artifact_manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint(
            {**state, **updates}, artifact_manifest, suffix="architecture_planning"
        )
    )
    return updates
