"""Deterministic enforcement of the Python production backend policy."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any


def _violation(
    rule_id: str,
    message: str,
    *,
    path: str = "",
    remediation: str = "",
    severity: str = "error",
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "path": path,
        "message": message,
        "remediation": remediation,
    }


def _has_any(root: Path, patterns: list[str]) -> bool:
    return any(any(root.glob(pattern)) for pattern in patterns)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def evaluate_policy_compliance(
    root: str | Path,
    policy: dict[str, Any],
    architecture: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate filesystem, dependency, and import-boundary policy rules."""
    project_root = Path(root)
    if not policy.get("enabled"):
        return {
            "status": "not_applicable",
            "passed": True,
            "policy_id": policy.get("id"),
            "policy_sha256": policy.get("sha256"),
            "violations": [],
        }

    violations: list[dict[str, str]] = []
    required_paths = {
        "BP-04": [
            "app/api/routes",
            "app/api/dependencies",
            "app/core",
            "app/domain",
            "app/application",
            "app/infrastructure/database",
            "app/infrastructure/repositories",
            "app/schemas",
            "app/middleware",
            "tests/unit",
            "tests/integration",
            "tests/api",
            "alembic/versions",
        ],
    }
    for rule_id, paths in required_paths.items():
        for relative in paths:
            if not (project_root / relative).is_dir():
                violations.append(
                    _violation(
                        rule_id,
                        "Required production architecture directory is missing.",
                        path=relative,
                        remediation=f"Create `{relative}` and place the appropriate layer code/tests there.",
                    )
                )

    required_files = {
        "BP-18": [".env.example"],
        "BP-24": ["pyproject.toml"],
        "BP-25": ["Dockerfile"],
        "BP-31": ["README.md"],
        "BP-32": ["Makefile"],
        "BP-10": ["alembic.ini"],
    }
    for rule_id, files in required_files.items():
        for relative in files:
            if not (project_root / relative).is_file():
                violations.append(
                    _violation(
                        rule_id,
                        "Required production deliverable is missing.",
                        path=relative,
                        remediation=f"Generate a complete `{relative}` consistent with the approved architecture.",
                    )
                )
    alternative_files = {
        "BP-25": (
            [
                "docker-compose.yml",
                "docker-compose.yaml",
                "compose.yml",
                "compose.yaml",
            ],
            "A Docker Compose configuration is missing.",
        ),
        "BP-26": (
            [".github/workflows/ci.yml", ".github/workflows/ci.yaml"],
            "The GitHub Actions CI workflow is missing.",
        ),
    }
    for rule_id, (files, message) in alternative_files.items():
        if not any((project_root / relative).is_file() for relative in files):
            violations.append(
                _violation(
                    rule_id,
                    message,
                    path=" or ".join(files),
                    remediation="Generate one of the documented production deliverables.",
                )
            )
    if not _has_any(project_root, ["alembic/versions/*.py"]):
        violations.append(
            _violation(
                "BP-10",
                "No Alembic schema migration was generated.",
                path="alembic/versions",
                remediation="Add an initial reversible migration for every approved data contract.",
            )
        )
    if not _has_any(
        project_root, [".pre-commit-config.yaml", ".pre-commit-config.yml"]
    ):
        violations.append(
            _violation(
                "BP-26",
                "Pre-commit configuration is missing.",
                path=".pre-commit-config.yaml",
                remediation="Configure Ruff and appropriate repository checks in pre-commit.",
            )
        )

    pyproject = _read(project_root / "pyproject.toml").lower()
    dependency_expectations = {
        "fastapi": "BP-01",
        "pydantic-settings": "BP-18",
        "sqlalchemy": "BP-10",
        "asyncpg": "BP-10",
        "alembic": "BP-10",
        "pytest": "BP-22",
        "pytest-asyncio": "BP-22",
        "ruff": "BP-23",
        "mypy": "BP-23",
        "opentelemetry": "BP-19",
        "prometheus": "BP-19",
    }
    for dependency, rule_id in dependency_expectations.items():
        if dependency not in pyproject:
            violations.append(
                _violation(
                    rule_id,
                    f"Required dependency or tool `{dependency}` is not declared.",
                    path="pyproject.toml",
                    remediation=f"Declare and configure `{dependency}` using uv-compatible pyproject metadata.",
                )
            )

    source_files = (
        sorted((project_root / "app").rglob("*.py"))
        if (project_root / "app").is_dir()
        else []
    )
    combined_source = "\n".join(_read(path) for path in source_files).lower()
    boundary_roots = ("app/domain/", "app/application/", "app/infrastructure/")
    for path in source_files:
        relative = path.relative_to(project_root).as_posix()
        content = _read(path)
        try:
            tree = ast.parse(content, filename=relative)
        except SyntaxError as exc:
            violations.append(
                _violation(
                    "BP-23",
                    f"Python syntax error: {exc.msg}",
                    path=relative,
                    remediation="Repair the file before any architecture review can pass.",
                )
            )
            continue
        imports: set[str] = set()
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Name):
                names.add(node.id)
        if relative.startswith(boundary_roots):
            if any(name.startswith(("fastapi", "starlette")) for name in imports):
                violations.append(
                    _violation(
                        "BP-35",
                        "FastAPI/Starlette leaked outside the API boundary.",
                        path=relative,
                        remediation="Move transport dependencies into app/api and expose a transport-independent port.",
                    )
                )
            if "HTTPException" in names:
                violations.append(
                    _violation(
                        "BP-35",
                        "HTTPException is forbidden outside the API boundary.",
                        path=relative,
                        remediation="Raise an AppError subtype and translate it in centralized API handlers.",
                    )
                )
        if relative.startswith(("app/domain/", "app/application/")) and any(
            name.startswith("sqlalchemy") for name in imports
        ):
            violations.append(
                _violation(
                    "BP-02",
                    "SQLAlchemy leaked into the domain/application layer.",
                    path=relative,
                    remediation="Depend on repository protocols; keep ORM implementation in infrastructure.",
                )
            )
        forbidden_internal_imports: tuple[str, ...] = ()
        if relative.startswith("app/domain/"):
            forbidden_internal_imports = (
                "app.api",
                "app.application",
                "app.infrastructure",
            )
        elif relative.startswith("app/application/"):
            forbidden_internal_imports = ("app.api", "app.infrastructure")
        if forbidden_internal_imports and any(
            imported.startswith(forbidden_internal_imports) for imported in imports
        ):
            violations.append(
                _violation(
                    "BP-02",
                    "An inner layer imports a forbidden outer layer.",
                    path=relative,
                    remediation="Invert the dependency through a domain/application protocol.",
                )
            )
        if "NotImplementedError" in content or "TODO:" in content or "TODO " in content:
            violations.append(
                _violation(
                    "BP-36",
                    "Placeholder or unfinished production code remains.",
                    path=relative,
                    remediation="Implement the behavior completely and add a focused test.",
                )
            )

    content_requirements = [
        ("BP-28", "/api/v1", "Versioned `/api/v1` routes are missing."),
        ("BP-06", "apperror", "A centralized AppError hierarchy is missing."),
        ("BP-18", "basesettings", "Pydantic Settings configuration is missing."),
        ("BP-19", "request_id", "Request/correlation ID propagation is missing."),
        ("BP-19", "opentelemetry", "OpenTelemetry instrumentation is missing."),
        ("BP-19", "prometheus", "Prometheus-compatible metrics are missing."),
    ]
    for rule_id, marker, message in content_requirements:
        if marker not in combined_source:
            violations.append(
                _violation(
                    rule_id,
                    message,
                    path="app",
                    remediation="Implement the policy requirement and add an automated test.",
                )
            )
    health_requirements = [
        ("/live", "A liveness route is missing."),
        ("/ready", "A readiness route is missing."),
    ]
    for endpoint, message in health_requirements:
        if endpoint not in combined_source or "health" not in combined_source:
            violations.append(
                _violation(
                    "BP-20",
                    message,
                    path="app/api",
                    remediation="Add separate health router liveness and dependency-aware readiness endpoints.",
                )
            )
    if "sqlite" in combined_source:
        violations.append(
            _violation(
                "BP-10",
                "SQLite appears in production application code; the production policy requires PostgreSQL.",
                path="app",
                remediation="Use PostgreSQL through SQLAlchemy async sessions; keep test substitutes outside app/.",
            )
        )

    dockerfile = _read(project_root / "Dockerfile").lower()
    if dockerfile and "user " not in dockerfile:
        violations.append(
            _violation(
                "BP-25",
                "Dockerfile does not switch to a non-root user.",
                path="Dockerfile",
                remediation="Create and use a non-root runtime user in the final image stage.",
            )
        )
    compose_path = next(
        (
            project_root / relative
            for relative in (
                "docker-compose.yml",
                "docker-compose.yaml",
                "compose.yml",
                "compose.yaml",
            )
            if (project_root / relative).is_file()
        ),
        project_root / "docker-compose.yml",
    )
    compose = _read(compose_path).lower()
    if compose and "postgres" not in compose:
        violations.append(
            _violation(
                "BP-10",
                "Local Compose configuration does not provide PostgreSQL.",
                path="docker-compose.yml",
                remediation="Add a health-checked PostgreSQL service and configure the API through environment variables.",
            )
        )

    auth_contracts = [
        contract
        for contract in architecture.get("api_contracts", [])
        if str(contract.get("path", "")).startswith("/api/v1/auth/")
    ]
    if auth_contracts:
        auth_expectations = [
            (
                "BP-17",
                "password",
                "Password hashing and verification behavior is missing.",
            ),
            ("BP-17", "token", "Secure authentication token handling is missing."),
            (
                "BP-17",
                "current_user",
                "An authenticated-current-user dependency is missing.",
            ),
        ]
        for rule_id, marker, message in auth_expectations:
            if marker not in combined_source:
                violations.append(
                    _violation(
                        rule_id,
                        message,
                        path="app",
                        remediation="Implement the approved authentication contract with focused security tests.",
                    )
                )
        test_source = "\n".join(
            _read(path).lower() for path in (project_root / "tests").rglob("*.py")
        )
        if not all(marker in test_source for marker in ("login", "unauthorized")):
            violations.append(
                _violation(
                    "BP-30",
                    "Authentication success and failure tests are incomplete.",
                    path="tests",
                    remediation="Test login success plus invalid credentials, missing token, and cross-user denial.",
                )
            )

    conditional = architecture.get("python_production", {}).get(
        "conditional_components", []
    )
    redis_decision = next(
        (item for item in conditional if item.get("component") == "redis"), {}
    )
    if redis_decision.get("decision") == "omit" and (
        "redis" in pyproject or "import redis" in combined_source
    ):
        violations.append(
            _violation(
                "BP-03",
                "Redis was introduced although the architecture explicitly omitted it.",
                path="pyproject.toml",
                remediation="Remove Redis or update the architecture with a concrete requirement and consistency strategy.",
            )
        )

    return {
        "status": "passed" if not violations else "failed",
        "passed": not violations,
        "policy_id": policy.get("id"),
        "policy_version": policy.get("version"),
        "policy_sha256": policy.get("sha256"),
        "checked_files": len(source_files),
        "violations": violations,
    }


def render_policy_compliance(result: dict[str, Any]) -> str:
    lines = [
        "# Python Production Policy Compliance",
        "",
        f"- Policy: `{result.get('policy_id', '')}`",
        f"- Version: `{result.get('policy_version', '')}`",
        f"- SHA-256: `{result.get('policy_sha256', '')}`",
        f"- Status: **{result.get('status', 'unknown')}**",
        f"- Python files checked: {result.get('checked_files', 0)}",
        "",
        "| Rule | Severity | Path | Finding | Remediation |",
        "| --- | --- | --- | --- | --- |",
    ]
    violations = result.get("violations", [])
    if not violations:
        lines.append("| — | — | — | No policy violations found | — |")
    for item in violations:
        values = [
            str(item.get(key, "")).replace("|", "\\|").replace("\n", " ")
            for key in ("rule_id", "severity", "path", "message", "remediation")
        ]
        lines.append(f"| {' | '.join(values)} |")
    lines.append("")
    return "\n".join(lines)


def policy_report_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
