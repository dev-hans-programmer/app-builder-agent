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
                    "dependencies": list(feature.get("dependencies", [])) or [epic["id"]],
                }
            )
            for component in feature.get("components", []):
                nodes.append(
                    {
                        "id": component["id"],
                        "title": component["title"],
                        "level": "component",
                        "dependencies": list(component.get("dependencies", [])) or [feature["id"]],
                    }
                )
                for task in component.get("tasks", []):
                    nodes.append(
                        {
                            "id": task["id"],
                            "title": task["title"],
                            "level": "task",
                            "dependencies": list(task.get("dependencies", [])) or [component["id"]],
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


def _topological_order(nodes: list[Dict[str, Any]], dependency_graph: Dict[str, list[str]]) -> list[str]:
    """Return a stable topological ordering for nodes in the plan."""
    in_degree: Dict[str, int] = {node["id"]: 0 for node in nodes}
    reverse_edges: Dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        for dependency in dependency_graph.get(node["id"], []):
            if dependency in in_degree:
                in_degree[node["id"]] += 1
                reverse_edges[dependency].append(node["id"])

    ready = deque(sorted(node_id for node_id, degree in in_degree.items() if degree == 0))
    ordered: list[str] = []

    while ready:
        node_id = ready.popleft()
        ordered.append(node_id)
        for dependent in sorted(reverse_edges.get(node_id, [])):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)

    return ordered


def _parallel_groups(nodes: list[Dict[str, Any]], ordered_specs: list[str]) -> list[list[str]]:
    """Group nodes by level for safe parallel execution."""
    level_map: Dict[str, str] = {node["id"]: node["level"] for node in nodes}
    stage_order = ["epic", "feature", "component", "task"]
    groups: list[list[str]] = []
    for level in stage_order:
        group = [spec_id for spec_id in ordered_specs if level_map.get(spec_id) == level]
        if group:
            groups.append(group)
    return groups


def build_execution_plan(spec_tree: Dict[str, Any], project_name: str) -> Dict[str, Any]:
    """Build a structured execution plan from a spec tree."""
    nodes = _collect_spec_nodes(spec_tree)
    dependency_graph = _build_dependency_graph(nodes)
    ordered_specs = _topological_order(nodes, dependency_graph)
    parallel_groups = _parallel_groups(nodes, ordered_specs)

    checkpoints = [f"checkpoint-after-{group[0]}" for group in parallel_groups]
    if not checkpoints and ordered_specs:
        checkpoints = [f"checkpoint-after-{ordered_specs[0]}"]

    plan = {
        "id": f"{project_name}-execution-plan",
        "title": f"Execution Plan for {project_name}",
        "ordered_specs": ordered_specs,
        "dependency_graph": dependency_graph,
        "parallel_groups": parallel_groups,
        "checkpoints": checkpoints,
        "retry_policy": {
            "max_attempts_per_spec": 2,
            "strategy": "exponential_backoff",
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

    plan = build_execution_plan(spec_tree, project_name)
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
