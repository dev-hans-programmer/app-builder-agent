"""Fast, task-scoped checks run before a dynamic task is accepted."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


class TaskVerificationError(RuntimeError):
    pass


def verify_python_task(output_dir: str | Path, patches: list[dict[str, Any]]) -> dict:
    root = Path(output_dir)
    python_files = sorted(
        {
            root / str(patch["path"])
            for patch in patches
            if str(patch.get("path", "")).endswith(".py")
            and (root / str(patch["path"])).is_file()
        }
    )
    checks: list[dict[str, Any]] = []
    syntax_errors: list[str] = []
    for path in python_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError) as error:
            syntax_errors.append(f"{path.relative_to(root)}: {error}")
    checks.append(
        {
            "category": "syntax",
            "status": "passed" if not syntax_errors else "failed",
            "files": [str(path.relative_to(root)) for path in python_files],
            "error": "\n".join(syntax_errors) or None,
        }
    )

    ruff = shutil.which("ruff")
    if ruff and python_files:
        relative_files = [str(path.relative_to(root)) for path in python_files]
        for category, arguments in (
            ("format", [ruff, "format", *relative_files]),
            ("lint", [ruff, "check", "--fix", *relative_files]),
        ):
            result = subprocess.run(
                arguments,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            checks.append(
                {
                    "category": category,
                    "status": "passed" if result.returncode == 0 else "failed",
                    "command": arguments,
                    "exit_code": result.returncode,
                    "stdout": result.stdout[-4_000:],
                    "stderr": result.stderr[-4_000:],
                }
            )

    failures = [check for check in checks if check["status"] == "failed"]
    result = {"passed": not failures, "checks": checks}
    if failures:
        details = "; ".join(
            f"{check['category']}: "
            f"{check.get('error') or check.get('stderr') or check.get('stdout') or 'failed'}"
            for check in failures
        )
        raise TaskVerificationError(details)
    return result
