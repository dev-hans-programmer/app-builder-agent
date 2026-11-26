"""Post-generation build, lint, type, test, and smoke quality gates."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.graph.runtime import ensure_workspace_layout, persist_job_checkpoint
from src.graph.state import BuilderState
from src.observability import append_event
from src.agents.policy_compliance import (
    evaluate_policy_compliance,
    policy_report_hash,
    render_policy_compliance,
)


CHECK_TIMEOUT_SECONDS = 180


def _safe_environment(*, category: str) -> dict[str, str]:
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "VIRTUAL_ENV" and not any(marker in key.upper() for marker in blocked)
    }
    if category == "container":
        # Compose interpolation needs a non-secret value for static validation.
        # Never forward the control plane's actual database password.
        environment["POSTGRES_PASSWORD"] = "app_builder_validation_only"
    return environment


def _run_check(
    stack: str,
    category: str,
    command: list[str] | None,
    cwd: Path,
    *,
    required: bool,
    skipped_reason: str = "",
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    if not command:
        return {
            "stack": stack,
            "category": category,
            "command": [],
            "command_display": "not configured",
            "status": "skipped",
            "required": required,
            "exit_code": None,
            "duration_ms": 0,
            "started_at": started_at,
            "ended_at": started_at,
            "stdout": "",
            "stderr": skipped_reason,
        }
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=_safe_environment(category=category),
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
        status = "passed" if result.returncode == 0 else "failed"
        return {
            "stack": stack,
            "category": category,
            "command": command,
            "command_display": " ".join(command),
            "status": status,
            "required": required,
            "exit_code": result.returncode,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "stdout": result.stdout[-12_000:],
            "stderr": result.stderr[-12_000:],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "stack": stack,
            "category": category,
            "command": command,
            "command_display": " ".join(command),
            "status": "failed",
            "required": required,
            "exit_code": None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "stdout": "",
            "stderr": str(exc),
        }


def _python_commands(
    root: Path, *, production_policy: bool = False
) -> list[tuple[str, list[str] | None, bool, str]]:
    if production_policy:
        uv = shutil.which("uv")
        docker = shutil.which("docker")
        project_root = str(root.resolve())
        uv_run = [uv, "run", "--project", project_root] if uv else []
        compose_file = next(
            (
                root / name
                for name in (
                    "docker-compose.yml",
                    "docker-compose.yaml",
                    "compose.yml",
                    "compose.yaml",
                )
                if (root / name).is_file()
            ),
            None,
        )
        return [
            (
                "dependencies",
                [uv, "lock", "--project", project_root] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "build",
                [*uv_run, "python", "-m", "compileall", "-q", "app"] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "format_apply",
                [*uv_run, "ruff", "format", "."] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "format",
                [*uv_run, "ruff", "format", "--check", "."] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "lint",
                [*uv_run, "ruff", "check", "."] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "type",
                [*uv_run, "mypy", "app"] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "test",
                [*uv_run, "pytest", "-q"] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "migration",
                [*uv_run, "alembic", "heads"] if uv else None,
                True,
                "uv is not installed",
            ),
            (
                "smoke",
                [
                    *uv_run,
                    "python",
                    "-c",
                    "from app.main import app; assert app is not None",
                ]
                if uv
                else None,
                True,
                "uv is not installed",
            ),
            (
                "container",
                [
                    docker,
                    "compose",
                    "-f",
                    str(compose_file.resolve()),
                    "config",
                    "--quiet",
                ]
                if docker and compose_file
                else None,
                False,
                (
                    "docker is not installed; static container policy checks still ran"
                    if not docker
                    else "No Compose file exists in the generated project; static policy checks still ran"
                ),
            ),
        ]
    requirements = root / "requirements.txt"
    uv = shutil.which("uv")
    runtime = [sys.executable]
    test_runtime = runtime
    if uv and requirements.is_file():
        uv_runtime = [
            uv,
            "run",
            "--isolated",
            "--with-requirements",
            "requirements.txt",
        ]
        runtime = [*uv_runtime, "python"]
        test_runtime = [*uv_runtime, "--with", "pytest", "python"]
    entry = next(
        (name for name in ("main.py", "app.py") if (root / name).is_file()), None
    )
    tests_exist = any(root.glob("test*.py")) or (root / "tests").is_dir()
    ruff = shutil.which("ruff")
    mypy = shutil.which("mypy")
    return [
        ("build", [*runtime, "-m", "compileall", "-q", "."], True, ""),
        (
            "lint",
            [ruff, "check", "."] if ruff else None,
            False,
            "ruff is not installed",
        ),
        ("type", [mypy, "."] if mypy else None, False, "mypy is not installed"),
        (
            "test",
            [*test_runtime, "-m", "pytest", "-q"] if tests_exist else None,
            True,
            "No Python tests were generated.",
        ),
        (
            "smoke",
            [
                *runtime,
                "-c",
                f"import {Path(entry).stem}; assert hasattr({Path(entry).stem}, 'app')",
            ]
            if entry
            else None,
            True,
            "No main.py or app.py entry point was generated.",
        ),
    ]


def _node_commands(root: Path) -> list[tuple[str, list[str] | None, bool, str]]:
    package_path = root / "package.json"
    if not package_path.is_file():
        return [
            (
                category,
                None,
                category in {"build", "test", "smoke"},
                "package.json was not generated",
            )
            for category in ("build", "lint", "type", "test", "smoke")
        ]
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        package = {}
    scripts = (
        package.get("scripts", {}) if isinstance(package.get("scripts"), dict) else {}
    )
    entry = package.get("main") or next(
        (
            name
            for name in ("server.js", "app.js", "index.js")
            if (root / name).is_file()
        ),
        None,
    )
    node = shutil.which("node")
    npm = shutil.which("npm")
    build_command = (
        [npm, "run", "build"]
        if npm and "build" in scripts
        else ([node, "--check", str(entry)] if node and entry else None)
    )
    return [
        (
            "dependencies",
            [npm, "install", "--ignore-scripts", "--no-audit", "--no-fund"]
            if npm
            else None,
            True,
            "npm is not installed.",
        ),
        (
            "build",
            build_command,
            True,
            "No build script or JavaScript entry point was generated.",
        ),
        (
            "lint",
            [npm, "run", "lint"] if npm and "lint" in scripts else None,
            False,
            "No lint script is configured.",
        ),
        (
            "type",
            [npm, "run", "typecheck"] if npm and "typecheck" in scripts else None,
            False,
            "No typecheck script is configured.",
        ),
        (
            "test",
            [npm, "test"] if npm and "test" in scripts else None,
            True,
            "No test script is configured.",
        ),
        (
            "smoke",
            [node, "--check", str(entry)] if node and entry else None,
            True,
            "Node.js or an application entry point is unavailable.",
        ),
    ]


def evaluate_stack(
    stack: str,
    output: dict[str, Any],
    *,
    backend_policy: dict[str, Any] | None = None,
    architecture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one selected stack and return structured command evidence."""
    if output.get("status") == "placeholder":
        checks = [
            _run_check(
                stack,
                category,
                None,
                Path.cwd(),
                required=category in {"build", "test", "smoke"},
                skipped_reason="No model output exists in offline mode.",
            )
            for category in ("build", "lint", "type", "test", "smoke")
        ]
        return {
            "stack": stack,
            "status": "not_evaluated",
            "passed": True,
            "checks": checks,
        }
    if output.get("status") != "success" or not output.get("output_dir"):
        return {
            "stack": stack,
            "status": "failed",
            "passed": False,
            "checks": [],
            "error": output.get("error", "Generation did not complete successfully."),
        }
    root = Path(output["output_dir"])
    policy = backend_policy or {}
    compliance: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = []
    if stack == "python" and policy.get("enabled"):
        compliance = evaluate_policy_compliance(root, policy, architecture or {})
        checks.append(
            {
                "stack": stack,
                "category": "architecture",
                "command": ["internal-policy-validator"],
                "command_display": "internal Python production-policy validator",
                "status": "passed" if compliance["passed"] else "failed",
                "required": True,
                "exit_code": 0 if compliance["passed"] else 1,
                "duration_ms": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "stdout": "",
                "stderr": "\n".join(
                    f"{item['rule_id']} {item['path']}: {item['message']} Remediation: {item['remediation']}"
                    for item in compliance.get("violations", [])
                ),
            }
        )
    definitions = (
        _python_commands(root, production_policy=bool(policy.get("enabled")))
        if stack == "python"
        else _node_commands(root)
    )
    checks.extend(
        [
            _run_check(
                stack,
                category,
                command,
                root,
                required=required,
                skipped_reason=reason,
            )
            for category, command, required, reason in definitions
        ]
    )
    passed = all(
        check["status"] == "passed"
        or (check["status"] == "skipped" and not check["required"])
        for check in checks
    )
    return {
        "stack": stack,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "checks": checks,
        "policy_compliance": compliance,
    }


def render_quality_report(result: dict[str, Any]) -> str:
    lines = [
        "# Quality Gate Report",
        "",
        f"**Overall status**: {result['status']}",
        f"**Passed**: {str(result['passed']).lower()}",
        "",
    ]
    for stack_result in result.get("stacks", []):
        lines.extend(
            [
                f"## {stack_result['stack'].title()}",
                "",
                f"**Status**: {stack_result['status']}",
                "",
                "| Check | Required | Status | Exit | Duration | Command |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for check in stack_result.get("checks", []):
            lines.append(
                f"| {check['category']} | {str(check['required']).lower()} | {check['status']} | "
                f"{check['exit_code'] if check['exit_code'] is not None else '—'} | "
                f"{check['duration_ms']} ms | `{check['command_display']}` |"
            )
        for check in stack_result.get("checks", []):
            if check["status"] == "failed" or check.get("stderr"):
                lines.extend(
                    [
                        "",
                        f"### {check['category'].title()} diagnostics",
                        "",
                        "```text",
                        (
                            check.get("stdout", "") + "\n" + check.get("stderr", "")
                        ).strip(),
                        "```",
                    ]
                )
        lines.append("")
    return "\n".join(lines)


def run_quality_gate(state: BuilderState) -> dict[str, Any]:
    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".", project_name=state.get("project_name")
    )
    selected: list[tuple[str, dict[str, Any]]] = []
    target = state.get("target_stack", "both")
    if target in {"python", "both"}:
        selected.append(("python", state.get("python_output") or {}))
    if target in {"nodejs", "both"}:
        selected.append(("nodejs", state.get("nodejs_output") or {}))
    stacks = [
        evaluate_stack(
            stack,
            output,
            backend_policy=state.get("backend_policy") or {},
            architecture=state.get("architecture_plan") or {},
        )
        for stack, output in selected
    ]
    passed = bool(stacks) and all(item["passed"] for item in stacks)
    result = {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "attempt": int(state.get("repair_attempt", 0)) + 1,
        "stacks": stacks,
    }
    verification_dir = Path(manifest["verification_dir"])
    verification_dir.mkdir(parents=True, exist_ok=True)
    report_path = verification_dir / "quality-report.md"
    report_path.write_text(render_quality_report(result), encoding="utf-8")
    result["artifact_path"] = str(report_path)
    manifest["quality_report_markdown"] = str(report_path)
    report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    for stack_result in stacks:
        compliance = stack_result.get("policy_compliance")
        if not compliance:
            continue
        compliance_path = verification_dir / "python-policy-compliance.md"
        compliance_path.write_text(
            render_policy_compliance(compliance), encoding="utf-8"
        )
        compliance["artifact_path"] = str(compliance_path)
        compliance["artifact_hash"] = policy_report_hash(compliance_path)
        manifest["policy_compliance_report_markdown"] = str(compliance_path)
    for stack_result in stacks:
        for check in stack_result.get("checks", []):
            append_event(
                state,
                {
                    "event_type": "quality_check_finished",
                    "step_id": f"quality_gate.{check['category']}",
                    "parent_step_id": "quality_gate",
                    "node": "quality_gate",
                    "phase": "verification",
                    "stack": stack_result["stack"],
                    "attempt": result["attempt"],
                    "status": check["status"],
                    "started_at": check.get("started_at"),
                    "ended_at": check.get("ended_at"),
                    "duration_ms": check.get("duration_ms"),
                    "command": check.get("command_display"),
                    "exit_code": check.get("exit_code"),
                    "retry_reason": (
                        f"{check['category']} check failed"
                        if check["status"] == "failed"
                        else None
                    ),
                    "verification_check": check["category"],
                    "expected": "exit code 0"
                    if check.get("command")
                    else "tool available",
                    "actual": (
                        f"exit code {check['exit_code']}"
                        if check.get("exit_code") is not None
                        else check["status"]
                    ),
                    "severity": "error" if check["status"] == "failed" else "info",
                    "output_artifacts": [str(report_path)],
                    "artifact_hashes": {str(report_path): report_hash},
                    "error_type": "CommandFailed"
                    if check["status"] == "failed"
                    else None,
                    "error_message": (
                        (check.get("stderr") or check.get("stdout") or "")[-2_000:]
                        if check["status"] == "failed"
                        else None
                    ),
                },
            )
    history = list(state.get("verification_results") or []) + [result]
    execution_trace = list(state.get("execution_trace") or [])
    if not execution_trace:
        for task in (state.get("execution_plan") or {}).get("tasks", []):
            execution_trace.append(
                {
                    "task_id": task.get("id"),
                    "spec_id": task.get("spec_id"),
                    "status": "generated"
                    if any(output.get("status") == "success" for _, output in selected)
                    else "skipped",
                }
            )
    repair_history = list(state.get("repair_history") or [])
    if passed and not repair_history:
        repair_history.append(
            {"status": "skipped", "reason": "All quality gates passed."}
        )
    updates = {
        "quality_results": result,
        "verification_results": history,
        "execution_trace": execution_trace,
        "repair_history": repair_history,
        "current_phase": "verification",
        "job_status": "running" if passed else "failed",
        "artifacts": manifest,
    }
    updates["checkpoint_path"] = str(
        persist_job_checkpoint({**state, **updates}, manifest, suffix="quality_gate")
    )
    return updates
