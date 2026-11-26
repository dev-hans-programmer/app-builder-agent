"""Requirement-to-contract-to-code-to-verification traceability gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState


def _selected_outputs(state: BuilderState) -> list[tuple[str, dict[str, Any]]]:
    target = state.get("target_stack", "both")
    outputs: list[tuple[str, dict[str, Any]]] = []
    if target in {"python", "both"}:
        outputs.append(("python", state.get("python_output") or {}))
    if target in {"nodejs", "both"}:
        outputs.append(("nodejs", state.get("nodejs_output") or {}))
    return outputs


def build_traceability_result(state: BuilderState) -> dict[str, Any]:
    requirements = state.get("requirements") or {}
    architecture = state.get("architecture_plan") or {}
    plan = state.get("execution_plan") or {}
    quality = state.get("quality_results") or {}
    outputs = _selected_outputs(state)
    offline = bool(outputs) and all(output.get("status") == "placeholder" for _, output in outputs)
    criteria_results: list[dict[str, Any]] = []

    for criterion in requirements.get("acceptance_criteria", []):
        criterion_id = criterion.get("id")
        contract_ids = [
            contract["id"]
            for contract in [
                *architecture.get("api_contracts", []),
                *architecture.get("data_contracts", []),
            ]
            if criterion_id in contract.get("acceptance_criteria_ids", [])
        ]
        task_ids = [
            task["id"]
            for task in plan.get("tasks", [])
            if criterion_id in task.get("acceptance_criteria_ids", [])
        ]
        patch_evidence: dict[str, list[str]] = {}
        test_evidence: dict[str, list[str]] = {}
        for stack, output in outputs:
            paths: list[str] = []
            for run in output.get("task_runs", []):
                if criterion_id in run.get("acceptance_criteria_ids", []):
                    paths.extend(patch.get("path", "") for patch in run.get("patches", []))
            patch_evidence[stack] = sorted(set(path for path in paths if path))
            test_evidence[stack] = sorted(
                {
                    patch.get("path", "")
                    for patch in output.get("patches", [])
                    if "test" in Path(patch.get("path", "")).name.lower()
                    or "spec" in Path(patch.get("path", "")).name.lower()
                }
                - {""}
            )
        quality_evidence = {
            result["stack"]: [
                f"{check['category']}:{check['status']}"
                for check in result.get("checks", [])
            ]
            for result in quality.get("stacks", [])
        }
        stacks_have_patches = all(patch_evidence.get(stack) for stack, _ in outputs)
        stacks_have_tests = all(test_evidence.get(stack) for stack, _ in outputs)
        satisfied = bool(
            contract_ids
            and task_ids
            and stacks_have_patches
            and stacks_have_tests
            and quality.get("passed")
        )
        status = "not_evaluated" if offline else "satisfied" if satisfied else "missing_evidence"
        criteria_results.append(
            {
                "id": criterion_id,
                "requirement": criterion.get("requirement", ""),
                "status": status,
                "contract_ids": contract_ids,
                "task_ids": task_ids,
                "patches": patch_evidence,
                "tests": test_evidence,
                "quality_evidence": quality_evidence,
                "missing": [
                    label
                    for label, present in (
                        ("contract", bool(contract_ids)),
                        ("executable task", bool(task_ids)),
                        ("code patch", stacks_have_patches),
                        ("acceptance test", stacks_have_tests),
                        ("passing quality gates", bool(quality.get("passed"))),
                    )
                    if not present
                ],
            }
        )
    passed = offline or (
        bool(criteria_results)
        and all(item["status"] == "satisfied" for item in criteria_results)
    )
    return {
        "status": "not_evaluated" if offline else "passed" if passed else "failed",
        "passed": passed,
        "criteria": criteria_results,
        "quality_status": quality.get("status", "missing"),
    }


def render_traceability_report(result: dict[str, Any]) -> str:
    lines = [
        "# Requirement Traceability",
        "",
        f"**Status**: {result['status']}",
        f"**Gate passed**: {str(result['passed']).lower()}",
        "",
        "| Criterion | Status | Contracts | Tasks | Patched files | Tests | Missing |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in result.get("criteria", []):
        patch_count = sum(len(paths) for paths in item.get("patches", {}).values())
        test_count = sum(len(paths) for paths in item.get("tests", {}).values())
        lines.append(
            f"| {item['id']} | {item['status']} | {', '.join(item['contract_ids']) or 'none'} | "
            f"{', '.join(item['task_ids']) or 'none'} | {patch_count} | {test_count} | "
            f"{', '.join(item['missing']) or 'none'} |"
        )
    lines.extend(["", "## Criterion Evidence", ""])
    for item in result.get("criteria", []):
        lines.extend(
            [
                f"### {item['id']}: {item['requirement']}",
                "",
                f"- Contracts: {', '.join(item['contract_ids']) or 'none'}",
                f"- Tasks: {', '.join(item['task_ids']) or 'none'}",
            ]
        )
        for stack, paths in item.get("patches", {}).items():
            lines.append(f"- {stack.title()} patches: {', '.join(paths) or 'none'}")
        for stack, paths in item.get("tests", {}).items():
            lines.append(f"- {stack.title()} acceptance tests: {', '.join(paths) or 'none'}")
        for stack, checks in item.get("quality_evidence", {}).items():
            lines.append(f"- {stack.title()} checks: {', '.join(checks) or 'none'}")
        lines.append("")
    return "\n".join(lines)


def check_requirement_traceability(state: BuilderState) -> dict[str, Any]:
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".", project_name=state.get("project_name")
    )
    result = build_traceability_result(state)
    reports_dir = Path(manifest["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "traceability.md"
    report_path.write_text(render_traceability_report(result), encoding="utf-8")
    result["artifact_path"] = str(report_path)
    manifest["traceability_report_markdown"] = str(report_path)
    updates = {
        "traceability_result": result,
        "current_phase": "traceability",
        "job_status": "running" if result["passed"] else "failed",
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, manifest, suffix="traceability")
    )
    return updates
