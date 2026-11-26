"""
Spec decomposition agent.

This module turns architecture artifacts into a hierarchical spec tree that can
feed later planning and execution phases.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def _ordered_module_names(architecture: Dict[str, Any]) -> list[str]:
    """Return architecture module names in a stable implementation order."""
    module_map = architecture.get("module_map", {}) or {}
    layers = list(architecture.get("layers", []) or [])
    ordered: list[str] = []

    for name in layers:
        if name in module_map and name not in ordered:
            ordered.append(name)

    for name in module_map:
        if name not in ordered:
            ordered.append(name)

    if not ordered:
        ordered.append("implementation")

    return ordered


def _normalize_concerns(concerns: Any) -> list[str]:
    if isinstance(concerns, list):
        cleaned = [str(concern).strip() for concern in concerns if str(concern).strip()]
        return cleaned or ["core behavior"]
    if concerns:
        text = str(concerns).strip()
        return [text] if text else ["core behavior"]
    return ["core behavior"]


def _build_spec_tasks(
    project_name: str,
    spec_id: str,
    module_name: str,
    concerns: list[str],
) -> list[Dict[str, Any]]:
    tasks: list[Dict[str, Any]] = []
    task_specs: list[tuple[str, str, list[str]]] = [
        (
            "scaffold",
            f"Create the {module_name} scaffold",
            [
                f"Create the module files and boundaries for {module_name}.",
                f"Keep the scaffold scoped to spec {spec_id}.",
            ],
        )
    ]

    for concern in concerns:
        task_specs.append(
            (
                "implement",
                f"Implement {concern}",
                [
                    f"Implement {concern} within {module_name}.",
                    "Keep the change limited to the current spec.",
                ],
            )
        )

    task_specs.append(
        (
            "verify",
            f"Verify the {module_name} spec",
            [
                f"Write focused tests for {module_name}.",
                "Confirm the outputs match the acceptance criteria.",
            ],
        )
    )

    for index, (kind, title, objective_lines) in enumerate(task_specs, start=1):
        task_id = f"{spec_id}-task-{index}"
        tasks.append(
            {
                "id": task_id,
                "title": title,
                "kind": kind,
                "level": "task",
                "objective": " ".join(objective_lines),
                "scope": [module_name, *concerns],
                "dependencies": [spec_id] if index > 1 else [],
                "acceptance_criteria": [
                    f"{module_name} work for this spec is implemented in isolation.",
                    f"{title} can be verified independently.",
                ],
                "verification_steps": [
                    "Review the implementation against the spec.md file.",
                    "Run the focused tests for this task.",
                ],
                "status": "planned",
            }
        )

    return tasks


def _build_spec_prompt(
    project_name: str,
    spec: Dict[str, Any],
    requirements: Dict[str, Any],
    architecture: Dict[str, Any],
) -> str:
    scope_items = spec.get("scope", [])
    acceptance_items = spec.get("acceptance_criteria", [])
    contract_ids = spec.get("contract_ids", [])
    task_lines = []
    for task in spec.get("tasks", []):
        task_lines.append(f"- {task.get('title', '')}: {task.get('objective', '')}")

    lines = [
        "# Implementation Prompt",
        "",
        f"Project: {project_name}",
        f"Spec: {spec.get('id', '')}",
        "",
        "Implement only this spec and keep the scope narrow.",
        "Use the PRD and technical design as the source of truth.",
        "Do not pre-build later specs.",
        "",
        "## Requirement Summary",
        str(requirements.get("summary", "")),
        "",
        "## Architecture Context",
        architecture.get("summary", ""),
        "",
        "## Scope",
        *[f"- {item}" for item in scope_items],
        "",
        "## Acceptance Criteria",
        *[f"- {item}" for item in acceptance_items],
        "",
        "## Contract IDs",
        *[f"- {item}" for item in contract_ids],
        "",
        "## Ordered Tasks",
        *task_lines,
        "",
        "## Execution Rules",
        "- Change only what this spec requires.",
        "- Keep the implementation generic and traceable.",
        "- Verify the result before moving on.",
        "",
    ]
    return "\n".join(lines)


def _build_spec_artifact(
    project_name: str,
    order: int,
    module_name: str,
    concerns: list[str],
    architecture: Dict[str, Any],
    requirements: Dict[str, Any],
    previous_spec_id: str | None,
) -> Dict[str, Any]:
    spec_slug = _slugify(module_name)
    spec_id = f"{project_name}-spec-{order:02d}-{spec_slug}"
    dependency_ids = [architecture["id"]]
    if previous_spec_id:
        dependency_ids.append(previous_spec_id)

    tasks = _build_spec_tasks(project_name, spec_id, module_name, concerns)
    scope = [module_name, *concerns] if concerns else [module_name]
    approved_criteria = [
        f"{item['id']}: {item['requirement']}"
        for item in requirements.get("acceptance_criteria", [])
        if item.get("status") == "approved"
    ]
    api_contract_ids = [item["id"] for item in architecture.get("api_contracts", [])]
    data_contract_ids = [item["id"] for item in architecture.get("data_contracts", [])]
    contract_ids = (
        api_contract_ids if module_name in {"transport", "application"} else []
    )
    if module_name in {"domain", "data", "application"}:
        contract_ids = [*contract_ids, *data_contract_ids]
    spec = {
        "id": spec_id,
        "title": f"{module_name.title()} Spec",
        "order": order,
        "level": "spec",
        "module_name": module_name,
        "folder_name": f"{order:02d}-spec-{spec_slug}",
        "objective": f"Implement the {module_name} responsibilities defined by the technical design.",
        "scope": scope,
        "dependencies": dependency_ids,
        "acceptance_criteria": [
            *approved_criteria,
            f"{module_name} behavior is implemented in isolation.",
            f"{module_name} is represented by a dedicated spec folder.",
            "The spec includes explicit tasks and a ready-to-use prompt.",
        ],
        "acceptance_criteria_ids": [
            item["id"]
            for item in requirements.get("acceptance_criteria", [])
            if item.get("status") == "approved"
        ],
        "contract_ids": list(dict.fromkeys(contract_ids)),
        "verification_steps": [
            f"Review {module_name} spec.md against the technical design.",
            f"Confirm {module_name} tasks.md captures the ordered work.",
            f"Use {module_name} prompt.md as the implementation prompt.",
        ],
        "implementation_notes": [
            "Keep the implementation scoped to the current spec.",
            "Avoid introducing assumptions not present in the requirement or design.",
        ],
        "prompt": "",
        "tasks": tasks,
        "owner": "spec-planning-agent",
        "status": "planned",
    }
    spec["prompt"] = _build_spec_prompt(project_name, spec, requirements, architecture)
    return spec


def _build_feature_from_spec(
    spec: Dict[str, Any], architecture: Dict[str, Any]
) -> Dict[str, Any]:
    feature_id = f"{spec['id']}-feature"
    components = [
        {
            "id": f"{feature_id}-component-1",
            "title": f"{spec['module_name'].title()} Workstream",
            "level": "component",
            "objective": spec["objective"],
            "scope": spec.get("scope", []),
            "dependencies": list(spec.get("dependencies", [])),
            "acceptance_criteria": list(spec.get("acceptance_criteria", [])),
            "verification_steps": list(spec.get("verification_steps", [])),
            "owner": spec.get("module_name", "spec-planning-agent"),
            "status": "planned",
            "tasks": spec.get("tasks", []),
        }
    ]
    return {
        "id": feature_id,
        "title": spec["title"],
        "level": "feature",
        "objective": spec["objective"],
        "scope": spec.get("scope", []),
        "dependencies": list(spec.get("dependencies", [])),
        "acceptance_criteria": list(spec.get("acceptance_criteria", [])),
        "verification_steps": list(spec.get("verification_steps", [])),
        "owner": spec.get("owner", "spec-planning-agent"),
        "status": spec.get("status", "planned"),
        "components": components,
        "module_name": spec.get("module_name", ""),
        "prompt": spec.get("prompt", ""),
        "folder_name": spec.get("folder_name", ""),
        "order": spec.get("order", 0),
    }


def _build_epic_from_specs(
    project_name: str,
    requirements: Dict[str, Any],
    architecture: Dict[str, Any],
    specs: list[Dict[str, Any]],
) -> Dict[str, Any]:
    epic_id = f"{project_name}-epic-implementation-foundation"
    features = [_build_feature_from_spec(spec, architecture) for spec in specs]
    return {
        "id": epic_id,
        "title": f"{project_name.replace('-', ' ').title()} Implementation",
        "level": "epic",
        "objective": "Translate the approved technical design into executable implementation work.",
        "scope": [
            "Spec decomposition",
            "Feature breakdown",
            "Implementation sequencing",
            "Verification mapping",
        ],
        "dependencies": [architecture["id"]],
        "acceptance_criteria": [
            "Every architecture module is represented by a spec folder.",
            "Each spec contains spec.md, tasks.md, and prompt.md.",
            "Each spec is ready for later execution.",
        ],
        "verification_steps": [
            "Check that every architecture module appears in the spec index.",
            "Confirm that each spec has its own folder and markdown files.",
        ],
        "owner": "spec-planning-agent",
        "status": "planned",
        "features": features,
    }


def _flatten_tasks_from_features(
    features: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    tasks: list[Dict[str, Any]] = []
    for feature in features:
        for component in feature.get("components", []):
            tasks.extend(component.get("tasks", []))
    return tasks


def _build_spec_index_markdown(spec_tree: Dict[str, Any]) -> str:
    lines = [
        "# Spec Breakdown",
        "",
        f"**ID**: {spec_tree['id']}",
        f"**Title**: {spec_tree['title']}",
        f"**Architecture Source**: {spec_tree['source_architecture_id']}",
        "",
        "## Ordered Specs",
    ]
    for spec in spec_tree.get("specs", []):
        lines.extend(
            [
                f"### {spec['order']:02d}. {spec['title']}",
                f"- ID: {spec['id']}",
                f"- Folder: `specs/{spec['folder_name']}`",
                f"- Objective: {spec['objective']}",
                f"- Tasks: {len(spec.get('tasks', []))}",
                "",
            ]
        )
    if not spec_tree.get("specs"):
        lines.append("- No specs were generated")
        lines.append("")
    return "\n".join(lines)


def _render_spec_markdown(spec: Dict[str, Any]) -> str:
    lines = [
        f"# {spec['title']}",
        "",
        f"**ID**: {spec['id']}",
        f"**Order**: {spec['order']}",
        f"**Module**: {spec['module_name']}",
        "",
        "## Objective",
        spec["objective"],
        "",
        "## Scope",
        *[f"- {item}" for item in spec.get("scope", [])],
        "",
        "## Dependencies",
        *[f"- {item}" for item in spec.get("dependencies", [])],
        "",
        "## Acceptance Criteria",
        *[f"- {item}" for item in spec.get("acceptance_criteria", [])],
        "",
        "## Linked Contracts",
        *[f"- {item}" for item in spec.get("contract_ids", [])],
        "",
        "## Verification Steps",
        *[f"- {item}" for item in spec.get("verification_steps", [])],
        "",
        "## Implementation Notes",
        *[f"- {item}" for item in spec.get("implementation_notes", [])],
        "",
    ]
    return "\n".join(lines)


def _render_tasks_markdown(spec: Dict[str, Any]) -> str:
    lines = [
        f"# Tasks for {spec['title']}",
        "",
        f"**Spec**: {spec['id']}",
        "",
        "| Status | Task | Objective |",
        "| --- | --- | --- |",
    ]
    for task in spec.get("tasks", []):
        lines.append(
            f"| {task.get('status', 'planned')} | {task.get('title', '')} | {task.get('objective', '')} |"
        )
    lines.extend(
        [
            "",
            "## Verification",
            *[f"- {item}" for item in spec.get("verification_steps", [])],
            "",
        ]
    )
    return "\n".join(lines)


def _render_prompt_markdown(spec: Dict[str, Any]) -> str:
    lines = [
        f"# Prompt for {spec['title']}",
        "",
        spec.get("prompt", ""),
        "",
    ]
    return "\n".join(lines)


def _persist_spec_documents(
    spec: Dict[str, Any],
    specs_dir: Path,
) -> Dict[str, str]:
    spec_dir = specs_dir / spec["folder_name"]
    spec_dir.mkdir(parents=True, exist_ok=True)

    spec_path = spec_dir / "spec.md"
    tasks_path = spec_dir / "tasks.md"
    prompt_path = spec_dir / "prompt.md"

    spec_path.write_text(_render_spec_markdown(spec), encoding="utf-8")
    tasks_path.write_text(_render_tasks_markdown(spec), encoding="utf-8")
    prompt_path.write_text(_render_prompt_markdown(spec), encoding="utf-8")

    return {
        "spec_markdown": str(spec_path),
        "tasks_markdown": str(tasks_path),
        "prompt_markdown": str(prompt_path),
        "folder": str(spec_dir),
    }


def _build_task(
    project_name: str,
    feature_slug: str,
    component_slug: str,
    index: int,
    component_label: str,
    module_name: str,
) -> Dict[str, Any]:
    task_id = f"{project_name}-task-{feature_slug}-{component_slug}-{index}"
    return {
        "id": task_id,
        "title": f"Implement {component_label}",
        "level": "task",
        "objective": f"Implement and verify {component_label} for the {module_name} module.",
        "scope": [component_label],
        "dependencies": [],
        "acceptance_criteria": [
            f"{component_label} exists in the codebase.",
            f"{component_label} is covered by targeted tests.",
        ],
        "verification_steps": [
            "Run the focused unit tests for the component.",
            "Validate the generated files or module behavior.",
        ],
        "owner": "implementation-agent",
        "status": "planned",
    }


def _build_component(
    project_name: str,
    feature_slug: str,
    module_name: str,
    concern: str,
    position: int,
) -> Dict[str, Any]:
    component_slug = _slugify(f"{module_name}-{position}-{concern}")
    label = concern or module_name
    component_id = f"{project_name}-component-{feature_slug}-{component_slug}"
    tasks = [
        _build_task(
            project_name,
            feature_slug,
            component_slug,
            1,
            f"{label} scaffold",
            module_name,
        ),
        _build_task(
            project_name,
            feature_slug,
            component_slug,
            2,
            f"{label} verification",
            module_name,
        ),
    ]
    return {
        "id": component_id,
        "title": f"{module_name.title()} - {label}",
        "level": "component",
        "objective": f"Provide the {label} capability for the {module_name} module.",
        "scope": [module_name, concern],
        "dependencies": [],
        "acceptance_criteria": [
            f"{module_name} supports {label}.",
            f"{module_name} can be verified independently.",
        ],
        "verification_steps": [
            f"Check the {module_name} behavior for {label}.",
            "Confirm the component passes its local tests.",
        ],
        "owner": module_name,
        "status": "planned",
        "tasks": tasks,
    }


def _build_feature(
    project_name: str,
    module_name: str,
    concerns: list[str],
    architecture: Dict[str, Any],
) -> Dict[str, Any]:
    feature_slug = _slugify(module_name)
    feature_id = f"{project_name}-feature-{feature_slug}"
    components = [
        _build_component(project_name, feature_slug, module_name, concern, index)
        for index, concern in enumerate(concerns, start=1)
    ]

    if not components:
        components = [
            _build_component(
                project_name,
                feature_slug,
                module_name,
                f"{module_name} implementation",
                1,
            )
        ]

    return {
        "id": feature_id,
        "title": f"{module_name.title()} Feature",
        "level": "feature",
        "objective": f"Implement the {module_name} responsibilities described by the architecture.",
        "scope": [module_name, *concerns],
        "dependencies": [architecture["id"]],
        "acceptance_criteria": [
            f"{module_name} is represented by concrete components.",
            f"{module_name} aligns with the architecture decisions.",
        ],
        "verification_steps": [
            f"Review the {module_name} component tree against the architecture.",
            f"Confirm the {module_name} feature resolves the requirement intent.",
        ],
        "owner": "spec-planning-agent",
        "status": "planned",
        "components": components,
    }


def _build_epic(
    project_name: str,
    requirements: Dict[str, Any],
    architecture: Dict[str, Any],
) -> Dict[str, Any]:
    epic_id = f"{project_name}-epic-implementation-foundation"
    module_map = architecture.get("module_map", {})
    features = [
        _build_feature(project_name, module_name, concerns, architecture)
        for module_name, concerns in module_map.items()
    ]

    return {
        "id": epic_id,
        "title": f"{project_name.replace('-', ' ').title()} Implementation",
        "level": "epic",
        "objective": "Translate the approved architecture into executable implementation work.",
        "scope": [
            "Spec decomposition",
            "Feature breakdown",
            "Implementation sequencing",
            "Verification mapping",
        ],
        "dependencies": [architecture["id"]],
        "acceptance_criteria": [
            "Every architecture module is represented by at least one feature.",
            "Each feature contains components, tasks, and verification steps.",
        ],
        "verification_steps": [
            "Check that every architecture module appears in the spec tree.",
            "Confirm that the resulting tree can drive planning and execution.",
        ],
        "owner": "spec-planning-agent",
        "status": "planned",
        "features": features,
    }


def build_spec_tree(
    requirements: Dict[str, Any],
    architecture: Dict[str, Any],
    project_name: str,
) -> Dict[str, Any]:
    """Build a hierarchical spec tree from requirements and architecture."""
    module_map = architecture.get("module_map", {}) or {}
    ordered_modules = _ordered_module_names(architecture)
    specs: list[Dict[str, Any]] = []
    previous_spec_id: str | None = None

    for order, module_name in enumerate(ordered_modules, start=1):
        concerns = _normalize_concerns(module_map.get(module_name, []))
        spec = _build_spec_artifact(
            project_name,
            order,
            module_name,
            concerns,
            architecture,
            requirements,
            previous_spec_id,
        )
        specs.append(spec)
        previous_spec_id = spec["id"]

    epic = _build_epic_from_specs(project_name, requirements, architecture, specs)
    features = epic.get("features", [])
    flat_index: list[str] = [epic["id"]]
    dependency_graph: Dict[str, list[str]] = {
        epic["id"]: list(epic.get("dependencies", []))
    }

    for spec, feature in zip(specs, features, strict=False):
        flat_index.append(spec["id"])
        dependency_graph[spec["id"]] = list(spec.get("dependencies", []))
        flat_index.append(feature["id"])
        dependency_graph[feature["id"]] = list(feature.get("dependencies", []))
        for component in feature.get("components", []):
            flat_index.append(component["id"])
            dependency_graph[component["id"]] = list(component.get("dependencies", []))
            for task in component.get("tasks", []):
                flat_index.append(task["id"])
                dependency_graph[task["id"]] = list(task.get("dependencies", []))

    return {
        "id": f"{project_name}-spec-tree",
        "title": f"Spec Tree for {project_name}",
        "source_architecture_id": architecture["id"],
        "source_requirement_id": requirements.get("id", ""),
        "objective": "Decompose the approved architecture into implementation-ready work.",
        "status": "draft",
        "epics": [epic],
        "specs": specs,
        "ordered_specs": [spec["id"] for spec in specs],
        "flat_index": flat_index,
        "dependency_graph": dependency_graph,
        "verification_summary": [
            "Each architecture module has a matching spec folder.",
            "Each spec includes spec.md, tasks.md, and prompt.md.",
            "Each spec contains explicit tasks and verification steps.",
        ],
    }


def render_spec_tree_markdown(spec_tree: Dict[str, Any]) -> str:
    """Render a spec tree to markdown for human review."""
    return _build_spec_index_markdown(spec_tree)


def persist_spec_tree_artifacts(
    spec_tree: Dict[str, Any],
    manifest: Dict[str, str],
    job_id: str,
) -> Dict[str, str]:
    """Persist the spec breakdown and per-spec folder artifacts."""
    specs_dir = Path(manifest["specs_dir"])
    specs_dir.mkdir(parents=True, exist_ok=True)

    md_path = specs_dir / "spec-breakdown.md"
    md_path.write_text(render_spec_tree_markdown(spec_tree), encoding="utf-8")

    per_spec_paths: Dict[str, Dict[str, str]] = {}
    for spec in spec_tree.get("specs", []):
        per_spec_paths[spec["id"]] = _persist_spec_documents(spec, specs_dir)
        spec["artifact_paths"] = per_spec_paths[spec["id"]]

    return {
        "spec_breakdown_markdown": str(md_path),
        "spec_tree_markdown": str(md_path),
        "spec_tree_json": str(md_path),
        "spec_index_json": str(md_path),
        "spec_documents": str(specs_dir),
    }


def validate_spec_tree(spec_tree: Dict[str, Any]) -> list[str]:
    """Validate basic structural properties of the generated spec tree."""
    errors: list[str] = []
    flat_index = spec_tree.get("flat_index", [])
    if not flat_index:
        errors.append("Spec tree must include at least one node.")

    if len(flat_index) != len(set(flat_index)):
        errors.append("Spec tree node ids must be unique.")

    if not spec_tree.get("epics"):
        errors.append("Spec tree must include at least one epic.")

    if spec_tree.get("specs") is not None and not spec_tree.get("specs"):
        errors.append("Spec tree must include at least one spec.")

    for spec in spec_tree.get("specs", []):
        if not spec.get("prompt"):
            errors.append(f"Spec {spec.get('id', 'unknown')} must include a prompt.")
        if not spec.get("tasks"):
            errors.append(f"Spec {spec.get('id', 'unknown')} must include tasks.")

    for epic in spec_tree.get("epics", []):
        if not epic.get("features"):
            errors.append(f"Epic {epic.get('id', 'unknown')} must include features.")
        for feature in epic.get("features", []):
            if not feature.get("components"):
                errors.append(
                    f"Feature {feature.get('id', 'unknown')} must include components."
                )
            for component in feature.get("components", []):
                if not component.get("tasks"):
                    errors.append(
                        f"Component {component.get('id', 'unknown')} must include tasks."
                    )
                for task in component.get("tasks", []):
                    if not task.get("verification_steps"):
                        errors.append(
                            f"Task {task.get('id', 'unknown')} must include verification steps."
                        )
    return errors


def generate_specs(state: BuilderState) -> Dict[str, Any]:
    """Generate and persist the spec tree from architecture."""
    requirements = state.get("requirements") or {}
    architecture = state.get("architecture_plan") or {}
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    project_name = state["project_name"]

    spec_tree = build_spec_tree(requirements, architecture, project_name)
    artifact_paths = persist_spec_tree_artifacts(spec_tree, manifest, state["job_id"])
    validation_errors = validate_spec_tree(spec_tree)

    updates = {
        "spec_tree": {
            **spec_tree,
            "artifact_paths": artifact_paths,
            "validation_errors": validation_errors,
        },
        "current_phase": "spec_decomposition",
        "job_status": "running",
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint(
            {**state, **updates}, manifest, suffix="spec_decomposition"
        )
    )
    return updates
