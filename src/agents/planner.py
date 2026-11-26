"""
Execution planning agent.

This module turns a spec tree into an executable plan with ordering,
dependency tracking, parallel groups, and persisted plan artifacts.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict

from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


def _collect_spec_nodes(spec_tree: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Flatten the spec tree into a list of nodes with hierarchy metadata."""
    nodes: list[Dict[str, Any]] = []
    for epic in spec_tree.get("epics", []):
        nodes.append(
            {
                "id": epic["id"],
                "title": epic["title"],
                "level": "epic",
                "dependencies": list(epic.get("dependencies", [])),
            }
        )
        for feature in epic.get("features", []):
            nodes.append(
                {
                    "id": feature["id"],
                    "title": feature["title"],
                    "level": "feature",
                    "dependencies": list(feature.get("dependencies", []))
                    or [epic["id"]],
                }
            )
            for component in feature.get("components", []):
                nodes.append(
                    {
                        "id": component["id"],
                        "title": component["title"],
                        "level": "component",
                        "dependencies": list(component.get("dependencies", []))
                        or [feature["id"]],
                    }
                )
                for task in component.get("tasks", []):
                    nodes.append(
                        {
                            "id": task["id"],
                            "title": task["title"],
                            "level": "task",
                            "dependencies": list(task.get("dependencies", []))
                            or [component["id"]],
                        }
                    )
    return nodes


def _build_dependency_graph(nodes: list[Dict[str, Any]]) -> Dict[str, list[str]]:
    """Create a dependency graph from the flattened spec nodes."""
    graph: Dict[str, list[str]] = {}
    for node in nodes:
        graph[node["id"]] = list(dict.fromkeys(node.get("dependencies", [])))
    return graph


def _detect_cycle(dependency_graph: Dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visited:
            return False
        if node_id in visiting:
            return True
        visiting.add(node_id)
        for dependency in dependency_graph.get(node_id, []):
            if dependency in dependency_graph and visit(dependency):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in dependency_graph)


def _topological_order(
    nodes: list[Dict[str, Any]], dependency_graph: Dict[str, list[str]]
) -> list[str]:
    """Return a stable topological ordering for nodes in the plan."""
    in_degree: Dict[str, int] = {node["id"]: 0 for node in nodes}
    reverse_edges: Dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        for dependency in dependency_graph.get(node["id"], []):
            if dependency in in_degree:
                in_degree[node["id"]] += 1
                reverse_edges[dependency].append(node["id"])

    ready = deque(
        sorted(node_id for node_id, degree in in_degree.items() if degree == 0)
    )
    ordered: list[str] = []

    while ready:
        node_id = ready.popleft()
        ordered.append(node_id)
        for dependent in sorted(reverse_edges.get(node_id, [])):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)

    return ordered


def _parallel_groups(
    nodes: list[Dict[str, Any]], ordered_specs: list[str]
) -> list[list[str]]:
    """Group nodes by level for safe parallel execution."""
    level_map: Dict[str, str] = {node["id"]: node["level"] for node in nodes}
    stage_order = ["epic", "feature", "component", "task"]
    groups: list[list[str]] = []
    for level in stage_order:
        group = [
            spec_id for spec_id in ordered_specs if level_map.get(spec_id) == level
        ]
        if group:
            groups.append(group)
    return groups


def _build_executable_tasks(
    spec_tree: Dict[str, Any],
    requirements: Dict[str, Any],
    architecture: Dict[str, Any],
) -> list[Dict[str, Any]]:
    acceptance_ids = [
        item["id"]
        for item in requirements.get("acceptance_criteria", [])
        if item.get("status") == "approved" and item.get("id")
    ]
    api_ids = [item["id"] for item in architecture.get("api_contracts", [])]
    data_ids = [item["id"] for item in architecture.get("data_contracts", [])]
    tasks: list[Dict[str, Any]] = []
    previous_task_id: str | None = None
    for index, spec in enumerate(spec_tree.get("specs", []), start=1):
        task_id = f"TASK-{index:03d}"
        module_name = str(spec.get("module_name") or "application")
        contract_ids = list(spec.get("contract_ids", []))
        if not contract_ids:
            contract_ids = (
                api_ids if module_name in {"transport", "application"} else []
            )
            if module_name in {"domain", "data", "application"}:
                contract_ids = [*contract_ids, *data_ids]
        tasks.append(
            {
                "id": task_id,
                "order": index,
                "spec_id": spec.get("id"),
                "title": f"Implement {spec.get('title', module_name)}",
                "objective": spec.get(
                    "objective", f"Implement the {module_name} module."
                ),
                "module": module_name,
                "scope": list(spec.get("scope", [])),
                "dependencies": [previous_task_id] if previous_task_id else [],
                "acceptance_criteria_ids": list(
                    spec.get("acceptance_criteria_ids", acceptance_ids)
                ),
                "contract_ids": list(dict.fromkeys(contract_ids)),
                "verification_categories": ["build", "lint", "type", "test", "smoke"],
                "status": "ready",
            }
        )
        previous_task_id = task_id
    return tasks


def _build_python_production_tasks(
    requirements: Dict[str, Any],
    architecture: Dict[str, Any],
    backend_policy: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """Build policy-aware foundation and vertical-slice Python tasks."""
    if not backend_policy.get("enabled"):
        return []
    criteria = list(requirements.get("acceptance_criteria", []))
    all_ids = [item["id"] for item in criteria if item.get("id")]
    auth_terms = (
        "auth",
        "login",
        "register",
        "user profile",
        "own data",
        "authorization",
    )
    auth_ids = [
        item["id"]
        for item in criteria
        if item.get("id")
        and any(term in str(item.get("requirement", "")).lower() for term in auth_terms)
    ]
    feature_ids = [
        criterion_id for criterion_id in all_ids if criterion_id not in auth_ids
    ]
    if not feature_ids:
        feature_ids = all_ids
    contracts = [
        *architecture.get("api_contracts", []),
        *architecture.get("data_contracts", []),
    ]

    def contract_ids(criterion_ids: list[str]) -> list[str]:
        return [
            item["id"]
            for item in contracts
            if set(item.get("acceptance_criteria_ids", [])) & set(criterion_ids)
        ]

    definitions: list[Dict[str, Any]] = [
        {
            "kind": "foundation",
            "title": "Create the production project foundation",
            "objective": "Create the policy-compliant package structure, pyproject, developer tooling, and explicit dependency boundaries.",
            "acceptance_criteria_ids": [],
            "contract_ids": [],
            "policy_sections": [1, 3, 4, 18, 23, 24, 31, 32, 35, 36],
            "allowed_paths": [
                "app/",
                "tests/",
                "pyproject.toml",
                ".python-version",
                ".env.example",
                "Makefile",
                "README.md",
            ],
        },
        {
            "kind": "platform",
            "title": "Implement the production platform foundation",
            "objective": "Implement typed configuration, transport-independent errors, async PostgreSQL access, Alembic, repositories, logging, telemetry, metrics, and health semantics.",
            "acceptance_criteria_ids": [],
            "contract_ids": [
                item["id"] for item in architecture.get("data_contracts", [])
            ],
            "policy_sections": [2, 6, 7, 8, 9, 10, 11, 12, 18, 19, 20, 27, 35],
            "allowed_paths": [
                "app/core/",
                "app/domain/errors/",
                "app/infrastructure/",
                "app/middleware/",
                "alembic/",
                "alembic.ini",
                "tests/integration/",
            ],
        },
    ]
    if auth_ids:
        definitions.append(
            {
                "kind": "authentication",
                "title": "Implement authentication and authorization as a vertical slice",
                "objective": "Implement user persistence, registration, login, caller identity, authorization, versioned API routes, schemas, and focused security tests without leaking HTTP into application/domain code.",
                "acceptance_criteria_ids": auth_ids,
                "contract_ids": contract_ids(auth_ids),
                "policy_sections": [2, 5, 6, 7, 8, 9, 10, 11, 17, 22, 30, 35],
                "allowed_paths": [
                    "app/core/",
                    "app/domain/",
                    "app/application/",
                    "app/infrastructure/",
                    "app/api/",
                    "app/schemas/",
                    "alembic/versions/",
                    "tests/",
                ],
            }
        )
    definitions.append(
        {
            "kind": "feature",
            "title": "Implement the requested business capabilities as vertical slices",
            "objective": "Implement every remaining approved capability end to end across domain, use cases, repository adapters, API contracts, migrations, and targeted tests.",
            "acceptance_criteria_ids": feature_ids,
            "contract_ids": contract_ids(feature_ids),
            "policy_sections": [
                2,
                5,
                6,
                7,
                8,
                9,
                10,
                11,
                12,
                21,
                22,
                23,
                28,
                29,
                30,
                35,
            ],
            "allowed_paths": [
                "app/domain/",
                "app/application/",
                "app/infrastructure/",
                "app/api/",
                "app/schemas/",
                "alembic/versions/",
                "tests/",
            ],
        }
    )
    definitions.append(
        {
            "kind": "delivery",
            "title": "Complete production operations and delivery",
            "objective": "Complete application composition, Docker, Compose, CI, pre-commit, documentation, production checks, and missing tests; remove placeholders and policy violations.",
            "acceptance_criteria_ids": all_ids,
            "contract_ids": [item["id"] for item in contracts],
            "policy_sections": [
                18,
                19,
                20,
                22,
                23,
                24,
                25,
                26,
                27,
                31,
                32,
                33,
                34,
                35,
                36,
            ],
            "allowed_paths": [
                "app/",
                "tests/",
                ".github/",
                "Dockerfile",
                "docker-compose.yml",
                ".pre-commit-config.yaml",
                "Makefile",
                "README.md",
                "docs/",
                "pyproject.toml",
                ".env.example",
            ],
        }
    )

    tasks: list[Dict[str, Any]] = []
    previous: str | None = None
    for index, definition in enumerate(definitions, start=1):
        task_id = f"PY-TASK-{index:03d}"
        tasks.append(
            {
                "id": task_id,
                "order": index,
                "stack": "python",
                "module": definition["kind"],
                "kind": definition["kind"],
                "title": definition["title"],
                "objective": definition["objective"],
                "dependencies": [previous] if previous else [],
                "acceptance_criteria_ids": definition["acceptance_criteria_ids"],
                "contract_ids": definition["contract_ids"],
                "policy_rule_ids": [
                    f"BP-{number:02d}" for number in definition["policy_sections"]
                ],
                "allowed_paths": definition["allowed_paths"],
                "verification_categories": [
                    "architecture",
                    "format",
                    "lint",
                    "type",
                    "test",
                    "migration",
                    "smoke",
                ],
                "status": "ready",
            }
        )
        previous = task_id
    return tasks


def build_execution_plan(
    spec_tree: Dict[str, Any],
    project_name: str,
    requirements: Dict[str, Any] | None = None,
    architecture: Dict[str, Any] | None = None,
    backend_policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a structured execution plan from a spec tree."""
    nodes = _collect_spec_nodes(spec_tree)
    dependency_graph = _build_dependency_graph(nodes)
    ordered_specs = _topological_order(nodes, dependency_graph)
    parallel_groups = _parallel_groups(nodes, ordered_specs)
    tasks = _build_executable_tasks(spec_tree, requirements or {}, architecture or {})
    python_tasks = _build_python_production_tasks(
        requirements or {}, architecture or {}, backend_policy or {}
    )

    checkpoints = [f"checkpoint-after-{group[0]}" for group in parallel_groups]
    if not checkpoints and ordered_specs:
        checkpoints = [f"checkpoint-after-{ordered_specs[0]}"]

    plan = {
        "id": f"{project_name}-execution-plan",
        "title": f"Execution Plan for {project_name}",
        "ordered_specs": ordered_specs,
        "ordered_tasks": [task["id"] for task in tasks],
        "tasks": tasks,
        "python_tasks": python_tasks,
        "ordered_python_tasks": [task["id"] for task in python_tasks],
        "dependency_graph": dependency_graph,
        "parallel_groups": parallel_groups,
        "checkpoints": checkpoints,
        "retry_policy": {
            "max_attempts_per_spec": 2,
            "max_repair_attempts": 2,
            "strategy": "targeted_repair",
        },
        "status": "draft",
    }
    return plan


def render_execution_plan_markdown(plan: Dict[str, Any]) -> str:
    """Render an execution plan as markdown."""
    lines = [
        "# Execution Plan",
        "",
        f"**ID**: {plan['id']}",
        f"**Title**: {plan['title']}",
        "",
        "## Executable Tasks",
        "",
        "| Order | ID | Module | Objective | Acceptance | Contracts |",
        "| ---: | --- | --- | --- | --- | --- |",
        *[
            "| {order} | {id} | {module} | {objective} | {acceptance} | {contracts} |".format(
                order=task.get("order", ""),
                id=task.get("id", ""),
                module=task.get("module", ""),
                objective=str(task.get("objective", "")).replace("|", "\\|"),
                acceptance=", ".join(task.get("acceptance_criteria_ids", [])) or "none",
                contracts=", ".join(task.get("contract_ids", [])) or "none",
            )
            for task in plan.get("tasks", [])
        ],
        "",
        "## Python Production Tasks",
        "",
        "| Order | ID | Kind | Objective | Acceptance | Contracts | Policy rules |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
        *[
            "| {order} | {id} | {kind} | {objective} | {acceptance} | {contracts} | {rules} |".format(
                order=task.get("order", ""),
                id=task.get("id", ""),
                kind=task.get("kind", ""),
                objective=str(task.get("objective", "")).replace("|", "\\|"),
                acceptance=", ".join(task.get("acceptance_criteria_ids", []))
                or "policy-only",
                contracts=", ".join(task.get("contract_ids", [])) or "none",
                rules=", ".join(task.get("policy_rule_ids", [])),
            )
            for task in plan.get("python_tasks", [])
        ],
        "",
        "## Ordered Specs",
        *[f"- {spec_id}" for spec_id in plan.get("ordered_specs", [])],
        "",
        "## Parallel Groups",
    ]
    for index, group in enumerate(plan.get("parallel_groups", []), start=1):
        lines.append(f"### Group {index}")
        lines.extend(f"- {spec_id}" for spec_id in group)
        lines.append("")
    lines.extend(
        [
            "## Checkpoints",
            *[f"- {checkpoint}" for checkpoint in plan.get("checkpoints", [])],
            "",
            "## Retry Policy",
        ]
    )
    for key, value in plan.get("retry_policy", {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def persist_execution_plan_artifacts(
    plan: Dict[str, Any],
    manifest: Dict[str, str],
    job_id: str,
) -> Dict[str, str]:
    """Persist the task plan as a single markdown file."""
    plans_dir = Path(manifest["plans_dir"])
    plans_dir.mkdir(parents=True, exist_ok=True)

    md_path = plans_dir / "tasks.md"
    md_path.write_text(render_execution_plan_markdown(plan), encoding="utf-8")

    return {
        "tasks_markdown": str(md_path),
        "execution_plan_markdown": str(md_path),
        "execution_plan_json": str(md_path),
    }


def validate_execution_plan(
    spec_tree: Dict[str, Any],
    plan: Dict[str, Any],
) -> list[str]:
    """Validate that the execution plan is complete and acyclic."""
    errors: list[str] = []
    nodes = _collect_spec_nodes(spec_tree)
    node_ids = {node["id"] for node in nodes}

    if not plan.get("ordered_specs"):
        errors.append("Execution plan must include ordered specs.")

    if set(plan.get("ordered_specs", [])) != node_ids:
        errors.append("Execution plan must include every spec node exactly once.")

    if _detect_cycle(plan.get("dependency_graph", {})):
        errors.append("Execution plan dependency graph contains a cycle.")

    for group in plan.get("parallel_groups", []):
        if len(group) != len(set(group)):
            errors.append("Parallel groups cannot contain duplicate spec ids.")

    return errors


def plan_execution(state: BuilderState) -> Dict[str, Any]:
    """Generate, validate, and persist an execution plan."""
    spec_tree = state.get("spec_tree") or {}
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    project_name = state["project_name"]

    plan = build_execution_plan(
        spec_tree,
        project_name,
        state.get("requirements") or {},
        state.get("architecture_plan") or {},
        state.get("backend_policy") or {},
    )
    artifact_paths = persist_execution_plan_artifacts(plan, manifest, state["job_id"])
    validation_errors = validate_execution_plan(spec_tree, plan)

    updates = {
        "execution_plan": {
            **plan,
            "artifact_paths": artifact_paths,
            "validation_errors": validation_errors,
        },
        "current_phase": "planning",
        "job_status": "running",
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, manifest, suffix="planning")
    )
    return updates
