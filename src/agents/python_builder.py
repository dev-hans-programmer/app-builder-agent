"""
Python/FastAPI builder agent.

This module implements the Python builder that uses the OpenAI API to generate
complete FastAPI applications from user prompts.
"""

import os
import time
import re
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from src.graph.state import BuilderState
from src.graph.runtime import ensure_workspace_layout
from src.observability import append_event, record_step_artifact
from src.observability.model_usage import model_observability
from src.agents.model_request import (
    chat_completion_options,
    completion_finish_reason,
    require_visible_completion,
)
from src.prompts.python_builder_prompt import (
    PYTHON_BUILDER_PROMPT_VERSION,
    create_python_prompt,
)
from openai import OpenAI


def parse_code_blocks(content: str) -> dict[str, str]:
    """
    Parse code blocks from model response.

    Expected format:
    ```filename: path/to/file.py
    [file contents]
    ```

    Args:
        content: Raw text from the model response

    Returns:
        Dictionary mapping file paths to file contents

    Example:
        >>> content = '''
        ... ```filename: main.py
        ... print("hello")
        ... ```
        ... ```filename: utils.py
        ... def helper():
        ...     pass
        ... ```
        ... '''
        >>> files = parse_code_blocks(content)
        >>> len(files)
        2
        >>> "main.py" in files
        True
        >>> "utils.py" in files
        True
    """
    files = {}

    # Regex pattern to match code blocks with filename marker
    # Pattern: ```filename: path/to/file.py\n[content]```
    pattern = r"```filename:\s*(.+?)\n(.*?)```"

    # Find all matches (DOTALL allows . to match newlines)
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        filepath = match.group(1).strip()
        file_content = match.group(2).strip()

        # Only add non-empty files
        if filepath and file_content:
            files[filepath] = file_content

    return files


def parse_generation_response(
    content: str, task: dict | None = None
) -> tuple[dict[str, str], dict]:
    """Parse the preferred traceable JSON envelope, with legacy fence fallback."""
    cleaned = content.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", cleaned)
        candidate = re.sub(r"\s*```$", "", candidate)
    else:
        candidate = cleaned
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return parse_code_blocks(content), {"format": "filename_blocks"}
        try:
            payload = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return parse_code_blocks(content), {"format": "filename_blocks"}
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        return parse_code_blocks(content), {"format": "filename_blocks"}
    if task and payload.get("task_id") not in {None, task.get("id")}:
        raise ValueError(
            f"Generation response task_id {payload.get('task_id')!r} does not match {task.get('id')!r}"
        )
    files: dict[str, str] = {}
    for item in payload["files"]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        file_content = item.get("content")
        if path and isinstance(file_content, str):
            if path in files:
                raise ValueError(
                    f"Generation response contains duplicate file path: {path}"
                )
            files[path] = file_content
    return files, {
        "format": "json",
        "acceptance_criteria_ids": payload.get("acceptance_criteria_ids", []),
        "policy_rule_ids": payload.get("policy_rule_ids", []),
    }


def validate_task_file_scope(files: dict[str, str], task: dict) -> None:
    """Reject model writes outside the task's declared ownership boundary."""
    allowed = [str(path).rstrip("/") for path in task.get("allowed_paths", [])]
    if not allowed:
        return
    for filepath in files:
        # pathlib already collapses a leading `./`. Do not use lstrip here:
        # it treats its argument as a character set and corrupts dotfiles such
        # as `.python-version` into `python-version`.
        normalized = Path(filepath).as_posix()
        if not any(
            normalized == path or normalized.startswith(f"{path}/") for path in allowed
        ):
            raise ValueError(
                f"Task {task.get('id')} attempted undeclared file {filepath!r}; "
                f"allowed paths: {', '.join(allowed)}"
            )


def validate_generation_metadata(metadata: dict, task: dict) -> None:
    """Require the model to echo the exact IDs that define task completion."""
    if metadata.get("format") != "json":
        raise ValueError(
            f"Task {task.get('id')} returned the legacy filename-block format; "
            "Python production tasks must return the documented JSON envelope"
        )
    expected = {
        "acceptance_criteria_ids": set(task.get("acceptance_criteria_ids", [])),
        "policy_rule_ids": set(task.get("policy_rule_ids", [])),
    }
    for field, expected_ids in expected.items():
        actual = metadata.get(field, [])
        if not isinstance(actual, list) or set(actual) != expected_ids:
            raise ValueError(
                f"Task {task.get('id')} returned incorrect {field}: "
                f"expected {sorted(expected_ids)}, got {actual!r}"
            )


def extract_response_text(response) -> str:
    """
    Extract assistant text from an OpenAI chat completion response.

    The OpenAI SDK returns the generated text under choices[0].message.content.
    """
    choices = getattr(response, "choices", None)
    if not choices:
        return ""

    message = choices[0].message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text", ""))
            else:
                parts.append(getattr(part, "text", ""))
        return "".join(parts)
    return ""


def _sha256_text(content: str | None) -> str | None:
    return (
        hashlib.sha256(content.encode("utf-8")).hexdigest()
        if content is not None
        else None
    )


def _safe_output_path(base_path: Path, filepath: str) -> Path:
    """Resolve a model-provided path and reject writes outside the build root."""
    if "\\" in filepath:
        raise ValueError(f"Generated path must use forward slashes: {filepath}")
    relative = Path(filepath)
    if relative.is_absolute():
        raise ValueError(f"Generated path must be relative: {filepath}")
    resolved_base = base_path.resolve()
    resolved = (resolved_base / relative).resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise ValueError(f"Generated path escapes the build directory: {filepath}")
    return resolved


def apply_file_patches(output_dir: str | Path, files: dict[str, str]) -> list[dict]:
    """Apply complete-file patches safely and return auditable hash metadata."""
    base_path = Path(output_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    patches: list[dict] = []
    for filepath, content in files.items():
        full_path = _safe_output_path(base_path, filepath)
        previous = (
            full_path.read_text(encoding="utf-8") if full_path.is_file() else None
        )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        patches.append(
            {
                "path": filepath,
                "operation": "created" if previous is None else "updated",
                "sha256_before": _sha256_text(previous),
                "sha256_after": _sha256_text(content),
            }
        )
    return patches


def read_project_files(
    output_dir: str | Path,
    *,
    max_files: int = 40,
    max_total_chars: int = 160_000,
) -> dict[str, str]:
    """Read a bounded text snapshot for the next task prompt."""
    base_path = Path(output_dir)
    if not base_path.exists():
        return {}
    ignored = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache"}
    result: dict[str, str] = {}
    total = 0
    for path in sorted(item for item in base_path.rglob("*") if item.is_file()):
        if any(part in ignored for part in path.parts):
            continue
        if path.name == ".env" or path.name.endswith((".pem", ".key", ".p12")):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if total + len(content) > max_total_chars:
            break
        result[str(path.relative_to(base_path))] = content
        total += len(content)
        if len(result) >= max_files:
            break
    return result


def write_files(output_dir: str, files: dict[str, str]) -> None:
    """
    Write generated files to disk.

    Creates the output directory and all necessary parent directories,
    then writes each file with UTF-8 encoding.

    Args:
        output_dir: Base directory for the project (e.g., "./projects/todo-api/builds/python")
        files: Dictionary mapping file paths to contents

    Example:
        >>> files = {
        ...     "main.py": "print('hello')",
        ...     "api/routes/users.py": "# user routes"
        ... }
        >>> write_files("./test-project", files)
        # Creates:
        # ./test-project/main.py
        # ./test-project/api/routes/users.py
    """
    apply_file_patches(output_dir, files)


def _generation_tasks(state: BuilderState, stack: str = "python") -> list[dict]:
    if stack == "python":
        python_tasks = list((state.get("execution_plan") or {}).get("python_tasks", []))
        if python_tasks:
            return python_tasks
    tasks = list((state.get("execution_plan") or {}).get("tasks", []))
    if tasks:
        return tasks
    return [
        {
            "id": "TASK-001",
            "title": "Generate the requested application",
            "objective": state["user_prompt"],
            "acceptance_criteria_ids": [],
            "contract_ids": [],
            "status": "ready",
        }
    ]


def _aggregate_observability(items: list[dict], model: str, version: str) -> dict:
    result: dict = {
        "model": model,
        "prompt_version": version,
        "model_calls": len(items),
    }
    for key in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "cached_tokens",
        "total_tokens",
        "estimated_cost",
    ):
        values = [
            item.get(key) for item in items if isinstance(item.get(key), (int, float))
        ]
        result[key] = sum(values) if values else None
    if items:
        result["prompt_hash"] = items[-1].get("prompt_hash")
        result["model_request_id"] = items[-1].get("model_request_id")
        result["model_request_ids"] = [
            item.get("model_request_id")
            for item in items
            if item.get("model_request_id")
        ]
        result["finish_reason"] = items[-1].get("finish_reason")
        result.update(
            {
                key: value
                for key, value in items[-1].items()
                if key.startswith("max_") or key == "reasoning_effort"
            }
        )
    return result


def record_generation_task_event(
    state: BuilderState,
    *,
    stack: str,
    event_type: str,
    task: dict,
    attempt: int,
    started_at: str,
    duration_ms: float | None = None,
    status: str,
    input_artifacts: list[str] | None = None,
    output_artifacts: list[str] | None = None,
    patches: list[dict] | None = None,
    observability: dict | None = None,
    error: Exception | None = None,
) -> None:
    """Emit task-level progress inside an instrumented builder node."""
    model = dict(observability or {})
    artifact_paths = [*(input_artifacts or []), *(output_artifacts or [])]
    artifact_hashes: dict[str, str] = {}
    for artifact_path in artifact_paths:
        try:
            path = Path(artifact_path)
            if path.is_file():
                artifact_hashes[artifact_path] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        except OSError:
            continue
    artifact_hashes.update(
        {
            patch["path"]: patch.get("sha256_after")
            for patch in patches or []
            if patch.get("sha256_after")
        }
    )
    append_event(
        state,
        {
            "event_type": event_type,
            "step_id": f"{stack}_builder.task",
            "parent_step_id": f"{stack}_builder",
            "node": f"{stack}_builder",
            "stack": stack,
            "spec_id": task.get("spec_id"),
            "task_id": task.get("id"),
            "acceptance_criterion_id": (task.get("acceptance_criteria_ids") or [None])[
                0
            ],
            "attempt": attempt,
            "status": status,
            "usage_detail": True,
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat()
            if event_type.endswith("finished")
            else None,
            "duration_ms": duration_ms,
            "input_artifacts": input_artifacts or [],
            "output_artifacts": output_artifacts or [],
            "artifact_hashes": artifact_hashes,
            "files_changed": [patch["path"] for patch in patches or []],
            "error_type": type(error).__name__ if error else None,
            "error_message": str(error) if error else None,
            **model,
        },
    )


def _legacy_build(state: BuilderState) -> dict:
    """
    Build a Python/FastAPI application using the OpenAI API.

    This is the main builder function that orchestrates the entire code generation
    process. It takes the user's requirements from state, calls the OpenAI API to
    generate code, parses the response, writes files to disk, and updates state.

    Steps:
    1. Validate OPENAI_API_KEY is available
    2. Create OpenAI client
    3. Generate prompt from user request and project name
        4. Call OpenAI API with appropriate parameters
    5. Parse response to extract file structure
    6. Write files to the project-scoped Python build directory
    7. Update state with success/failure results
    8. Track build time for performance monitoring

    Args:
        state: Current workflow state containing user_prompt, project_name, etc.

    Returns:
        Dictionary with python_output field for state update (LangGraph pattern)

    Example:
        >>> state = {
        ...     "user_prompt": "Build a todo API",
        ...     "project_name": "todo-api",
        ...     "errors": []
        ... }
        >>> result = build(state)
        >>> result["python_output"]["status"]
        'success'
        >>> result["python_output"]["file_count"]
        3
    """
    start_time = time.time()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    observability = {
        "model": model,
        "prompt_version": PYTHON_BUILDER_PROMPT_VERSION,
    }

    try:
        manifest = state.get("artifacts") or ensure_workspace_layout(
            ".",
            project_name=state.get("project_name"),
        )
        prompt = create_python_prompt(
            state["user_prompt"],
            state["project_name"],
        )
        observability = model_observability(
            model=model,
            prompt=prompt,
            prompt_version=PYTHON_BUILDER_PROMPT_VERSION,
        )
        record_step_artifact("prompt.txt", prompt)

        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print(
                "[Python Builder] ⚠️  OPENAI_API_KEY not found; using offline placeholder output"
            )
            build_time = time.time() - start_time
            return {
                "python_output": {
                    "status": "placeholder",
                    "message": "OPENAI_API_KEY not found; skipping model call",
                    "output_dir": None,
                    "files_created": [],
                    "framework": "FastAPI",
                    "file_count": 0,
                    "observability": observability,
                },
                "python_build_time": build_time,
            }

        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        request_options = chat_completion_options(model)

        print(f"[Python Builder] Generating code for: {state['project_name']}")

        # Call OpenAI API
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **request_options,
        )

        # Extract text from response
        content = extract_response_text(response)
        observability = model_observability(
            model=model,
            prompt=prompt,
            prompt_version=PYTHON_BUILDER_PROMPT_VERSION,
            response=response,
        )
        observability.update(request_options)
        record_step_artifact(
            "response.json",
            {
                "id": getattr(response, "id", None),
                "model": getattr(response, "model", model),
                "content": content,
                "finish_reason": completion_finish_reason(response),
                "usage": observability,
            },
        )
        require_visible_completion(content, response, request_options)

        # Parse files from response
        files = parse_code_blocks(content)

        if not files:
            raise ValueError("No files generated from model response")

        # Write files to disk
        output_dir = Path(manifest["builds_dir"]) / "python"
        write_files(output_dir, files)

        # Calculate build time
        build_time = time.time() - start_time

        print(f"[Python Builder] ✓ Created {len(files)} files in {output_dir}")
        print(f"[Python Builder] Build time: {build_time:.2f}s")

        # Return state updates (LangGraph pattern)
        return {
            "python_output": {
                "status": "success",
                "output_dir": str(output_dir),
                "files_created": list(files.keys()),
                "artifact_paths": [str(output_dir / filepath) for filepath in files],
                "framework": "FastAPI",
                "file_count": len(files),
                "observability": observability,
            },
            "python_build_time": build_time,
        }

    except Exception as e:
        build_time = time.time() - start_time
        error_msg = f"Python builder failed: {str(e)}"

        print(f"[Python Builder] ✗ Error: {error_msg}")
        print(f"[Python Builder] Build time: {build_time:.2f}s")

        # Return state updates with error
        return {
            "python_output": {
                "status": "failed",
                "error": str(e),
                "observability": observability,
            },
            "python_build_time": build_time,
            # `errors` has a LangGraph append reducer, so return only the new item.
            "errors": [error_msg],
        }


def build(state: BuilderState) -> dict:
    """Generate the Python application one executable task at a time."""
    start_time = time.time()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    observability: dict = {
        "model": model,
        "prompt_version": PYTHON_BUILDER_PROMPT_VERSION,
    }
    current_task: dict | None = None
    current_task_started = ""
    current_task_clock: float | None = None
    current_input_artifacts: list[str] = []
    current_usage: dict = {}
    task_runs: list[dict] = []
    output_dir: Path | None = None
    try:
        manifest = state.get("artifacts") or ensure_workspace_layout(
            ".", project_name=state.get("project_name")
        )
        output_dir = Path(manifest["builds_dir"]) / "python"
        tasks = _generation_tasks(state, "python")
        api_key = os.getenv("OPENAI_API_KEY")
        first_prompt = create_python_prompt(
            state["user_prompt"],
            state["project_name"],
            task=tasks[0],
            requirements=state.get("requirements") or {},
            architecture=state.get("architecture_plan") or {},
            current_files=read_project_files(output_dir),
            backend_policy=state.get("backend_policy") or {},
        )
        observability = model_observability(
            model=model,
            prompt=first_prompt,
            prompt_version=PYTHON_BUILDER_PROMPT_VERSION,
        )
        if not api_key:
            record_step_artifact("prompt.txt", first_prompt)
            print("[Python Builder] ⚠️  OPENAI_API_KEY not found; skipping model calls")
            return {
                "python_output": {
                    "status": "placeholder",
                    "message": "OPENAI_API_KEY not found; skipping model call",
                    "output_dir": None,
                    "files_created": [],
                    "framework": "FastAPI",
                    "file_count": 0,
                    "patches": [],
                    "observability": observability,
                },
                "python_build_time": time.time() - start_time,
            }

        client = OpenAI(api_key=api_key)
        request_options = chat_completion_options(model)
        usage_items: list[dict] = []
        all_paths: list[str] = []
        print(
            f"[Python Builder] Generating {len(tasks)} task(s) for: {state['project_name']}"
        )
        for index, task in enumerate(tasks, start=1):
            current_task = task
            current_task_started = datetime.now(timezone.utc).isoformat()
            current_task_clock = time.perf_counter()
            current_files = read_project_files(output_dir)
            current_input_artifacts = [str(output_dir / path) for path in current_files]
            prompt = create_python_prompt(
                state["user_prompt"],
                state["project_name"],
                task=task,
                requirements=state.get("requirements") or {},
                architecture=state.get("architecture_plan") or {},
                current_files=current_files,
                backend_policy=state.get("backend_policy") or {},
            )
            prompt_artifact = (
                "prompt.txt" if len(tasks) == 1 else f"task-{index:02d}-prompt.txt"
            )
            response_artifact = (
                "response.json"
                if len(tasks) == 1
                else f"task-{index:02d}-response.json"
            )
            prompt_path = record_step_artifact(prompt_artifact, prompt)
            record_generation_task_event(
                state,
                stack="python",
                event_type="task_started",
                task=task,
                attempt=1,
                started_at=current_task_started,
                status="started",
                input_artifacts=[
                    *current_input_artifacts,
                    *([prompt_path] if prompt_path else []),
                ],
            )
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **request_options,
            )
            content = extract_response_text(response)
            usage = model_observability(
                model=model,
                prompt=prompt,
                prompt_version=PYTHON_BUILDER_PROMPT_VERSION,
                response=response,
            )
            usage.update(request_options)
            current_usage = usage
            usage_items.append(usage)
            response_path = record_step_artifact(
                response_artifact,
                {
                    "id": getattr(response, "id", None),
                    "model": getattr(response, "model", model),
                    "content": content,
                    "finish_reason": completion_finish_reason(response),
                    "usage": usage,
                },
            )
            require_visible_completion(content, response, request_options)
            files, response_metadata = parse_generation_response(content, task)
            if not files:
                raise ValueError(
                    f"No files generated for {task.get('id', f'TASK-{index:03d}')}"
                )
            if (state.get("backend_policy") or {}).get("enabled"):
                validate_generation_metadata(response_metadata, task)
            validate_task_file_scope(files, task)
            patches = apply_file_patches(output_dir, files)
            all_paths.extend(files)
            task_runs.append(
                {
                    "task_id": task.get("id"),
                    "spec_id": task.get("spec_id"),
                    "status": "completed",
                    "acceptance_criteria_ids": task.get("acceptance_criteria_ids", []),
                    "contract_ids": task.get("contract_ids", []),
                    "policy_rule_ids": task.get("policy_rule_ids", []),
                    "response_format": response_metadata.get("format"),
                    "patches": patches,
                }
            )
            record_generation_task_event(
                state,
                stack="python",
                event_type="task_finished",
                task=task,
                attempt=1,
                started_at=current_task_started,
                duration_ms=round((time.perf_counter() - current_task_clock) * 1000, 2),
                status="succeeded",
                input_artifacts=current_input_artifacts,
                output_artifacts=[
                    *[str(output_dir / path) for path in files],
                    *([response_path] if response_path else []),
                ],
                patches=patches,
                observability=usage,
            )
            current_task = None

        observability = _aggregate_observability(
            usage_items, model, PYTHON_BUILDER_PROMPT_VERSION
        )
        files_created = sorted(set(all_paths))
        build_time = time.time() - start_time
        print(f"[Python Builder] ✓ Applied {len(task_runs)} task(s) in {output_dir}")
        return {
            "python_output": {
                "status": "success",
                "output_dir": str(output_dir),
                "files_created": files_created,
                "artifact_paths": [str(output_dir / path) for path in files_created],
                "framework": "FastAPI",
                "file_count": len(files_created),
                "task_runs": task_runs,
                "patches": [patch for run in task_runs for patch in run["patches"]],
                "observability": observability,
            },
            "python_build_time": build_time,
        }
    except Exception as exc:
        if current_task is not None and current_task_clock is not None:
            try:
                record_generation_task_event(
                    state,
                    stack="python",
                    event_type="task_finished",
                    task=current_task,
                    attempt=1,
                    started_at=current_task_started,
                    duration_ms=round(
                        (time.perf_counter() - current_task_clock) * 1000, 2
                    ),
                    status="failed",
                    input_artifacts=current_input_artifacts,
                    observability=current_usage,
                    error=exc,
                )
            except Exception:
                pass
        build_time = time.time() - start_time
        error_msg = f"Python builder failed: {exc}"
        print(f"[Python Builder] ✗ Error: {error_msg}")
        return {
            "python_output": {
                "status": "failed",
                "error": str(exc),
                "output_dir": str(output_dir) if output_dir else None,
                "task_runs": task_runs,
                "patches": [patch for run in task_runs for patch in run["patches"]],
                "observability": observability,
            },
            "python_build_time": build_time,
            "errors": [error_msg],
        }
