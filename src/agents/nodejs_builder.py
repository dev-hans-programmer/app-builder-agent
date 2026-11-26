"""
Node.js/Express builder agent.

This module implements the Node.js builder that uses the OpenAI API to generate
complete Express.js applications from user prompts.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from src.graph.state import BuilderState
from src.graph.runtime import ensure_workspace_layout
from src.observability import record_step_artifact
from src.observability.model_usage import model_observability
from src.agents.model_request import (
    chat_completion_options,
    completion_finish_reason,
    require_visible_completion,
)
from src.prompts.nodejs_builder_prompt import (
    NODEJS_BUILDER_PROMPT_VERSION,
    create_nodejs_prompt,
)

# Reuse utilities from Python builder
from src.agents.python_builder import (
    _aggregate_observability,
    _generation_tasks,
    apply_file_patches,
    extract_response_text,
    parse_code_blocks,
    read_project_files,
    record_generation_task_event,
    write_files,
)
from openai import OpenAI


def _legacy_build(state: BuilderState) -> dict:
    """
    Build a Node.js/Express application using the OpenAI API.

    This is the main builder function that orchestrates the entire code generation
    process for Node.js/Express backends. It follows the same pattern as the
    Python builder but generates Express.js code instead.

    Steps:
    1. Validate OPENAI_API_KEY is available
    2. Create OpenAI client
    3. Generate prompt from user request and project name
        4. Call OpenAI API with appropriate parameters
    5. Parse response to extract file structure
    6. Write files to the project-scoped Node.js build directory
    7. Update state with success/failure results
    8. Track build time for performance monitoring

    Args:
        state: Current workflow state containing user_prompt, project_name, etc.

    Returns:
        Dictionary with nodejs_output field for state update (LangGraph pattern)

    Example:
        >>> state = {
        ...     "user_prompt": "Build a todo API",
        ...     "project_name": "todo-api",
        ...     "errors": []
        ... }
        >>> result = build(state)
        >>> result["nodejs_output"]["status"]
        'success'
        >>> result["nodejs_output"]["file_count"]
        5
    """
    start_time = time.time()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    observability = {
        "model": model,
        "prompt_version": NODEJS_BUILDER_PROMPT_VERSION,
    }

    try:
        manifest = state.get("artifacts") or ensure_workspace_layout(
            ".",
            project_name=state.get("project_name"),
        )
        prompt = create_nodejs_prompt(
            state["user_prompt"],
            state["project_name"],
        )
        observability = model_observability(
            model=model,
            prompt=prompt,
            prompt_version=NODEJS_BUILDER_PROMPT_VERSION,
        )
        record_step_artifact("prompt.txt", prompt)

        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print(
                "[Node.js Builder] ⚠️  OPENAI_API_KEY not found; using offline placeholder output"
            )
            build_time = time.time() - start_time
            return {
                "nodejs_output": {
                    "status": "placeholder",
                    "message": "OPENAI_API_KEY not found; skipping model call",
                    "output_dir": None,
                    "files_created": [],
                    "framework": "Express.js",
                    "file_count": 0,
                    "observability": observability,
                },
                "nodejs_build_time": build_time,
            }

        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        request_options = chat_completion_options(model)

        print(f"[Node.js Builder] Generating code for: {state['project_name']}")

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
            prompt_version=NODEJS_BUILDER_PROMPT_VERSION,
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
        output_dir = Path(manifest["builds_dir"]) / "nodejs"
        write_files(output_dir, files)

        # Calculate build time
        build_time = time.time() - start_time

        print(f"[Node.js Builder] ✓ Created {len(files)} files in {output_dir}")
        print(f"[Node.js Builder] Build time: {build_time:.2f}s")

        # Return state updates (LangGraph pattern)
        return {
            "nodejs_output": {
                "status": "success",
                "output_dir": str(output_dir),
                "files_created": list(files.keys()),
                "artifact_paths": [str(output_dir / filepath) for filepath in files],
                "framework": "Express.js",
                "file_count": len(files),
                "observability": observability,
            },
            "nodejs_build_time": build_time,
        }

    except Exception as e:
        build_time = time.time() - start_time
        error_msg = f"Node.js builder failed: {str(e)}"

        print(f"[Node.js Builder] ✗ Error: {error_msg}")
        print(f"[Node.js Builder] Build time: {build_time:.2f}s")

        # Return state updates with error
        return {
            "nodejs_output": {
                "status": "failed",
                "error": str(e),
                "observability": observability,
            },
            "nodejs_build_time": build_time,
            # `errors` has a LangGraph append reducer, so return only the new item.
            "errors": [error_msg],
        }


def build(state: BuilderState) -> dict:
    """Generate the Node.js application one executable task at a time."""
    start_time = time.time()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    observability: dict = {
        "model": model,
        "prompt_version": NODEJS_BUILDER_PROMPT_VERSION,
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
        output_dir = Path(manifest["builds_dir"]) / "nodejs"
        tasks = _generation_tasks(state)
        api_key = os.getenv("OPENAI_API_KEY")
        first_prompt = create_nodejs_prompt(
            state["user_prompt"],
            state["project_name"],
            task=tasks[0],
            requirements=state.get("requirements") or {},
            architecture=state.get("architecture_plan") or {},
            current_files=read_project_files(output_dir),
        )
        observability = model_observability(
            model=model,
            prompt=first_prompt,
            prompt_version=NODEJS_BUILDER_PROMPT_VERSION,
        )
        if not api_key:
            record_step_artifact("prompt.txt", first_prompt)
            print("[Node.js Builder] ⚠️  OPENAI_API_KEY not found; skipping model calls")
            return {
                "nodejs_output": {
                    "status": "placeholder",
                    "message": "OPENAI_API_KEY not found; skipping model call",
                    "output_dir": None,
                    "files_created": [],
                    "framework": "Express.js",
                    "file_count": 0,
                    "patches": [],
                    "observability": observability,
                },
                "nodejs_build_time": time.time() - start_time,
            }

        client = OpenAI(api_key=api_key)
        request_options = chat_completion_options(model)
        usage_items: list[dict] = []
        all_paths: list[str] = []
        print(f"[Node.js Builder] Generating {len(tasks)} task(s) for: {state['project_name']}")
        for index, task in enumerate(tasks, start=1):
            current_task = task
            current_task_started = datetime.now(timezone.utc).isoformat()
            current_task_clock = time.perf_counter()
            current_files = read_project_files(output_dir)
            current_input_artifacts = [str(output_dir / path) for path in current_files]
            prompt = create_nodejs_prompt(
                state["user_prompt"],
                state["project_name"],
                task=task,
                requirements=state.get("requirements") or {},
                architecture=state.get("architecture_plan") or {},
                current_files=current_files,
            )
            prompt_artifact = "prompt.txt" if len(tasks) == 1 else f"task-{index:02d}-prompt.txt"
            response_artifact = "response.json" if len(tasks) == 1 else f"task-{index:02d}-response.json"
            prompt_path = record_step_artifact(prompt_artifact, prompt)
            record_generation_task_event(
                state,
                stack="nodejs",
                event_type="task_started",
                task=task,
                attempt=1,
                started_at=current_task_started,
                status="started",
                input_artifacts=[*current_input_artifacts, *([prompt_path] if prompt_path else [])],
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
                prompt_version=NODEJS_BUILDER_PROMPT_VERSION,
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
            files = parse_code_blocks(content)
            if not files:
                raise ValueError(f"No files generated for {task.get('id', f'TASK-{index:03d}')}")
            patches = apply_file_patches(output_dir, files)
            all_paths.extend(files)
            task_runs.append(
                {
                    "task_id": task.get("id"),
                    "spec_id": task.get("spec_id"),
                    "status": "completed",
                    "acceptance_criteria_ids": task.get("acceptance_criteria_ids", []),
                    "contract_ids": task.get("contract_ids", []),
                    "patches": patches,
                }
            )
            record_generation_task_event(
                state,
                stack="nodejs",
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
            usage_items, model, NODEJS_BUILDER_PROMPT_VERSION
        )
        files_created = sorted(set(all_paths))
        build_time = time.time() - start_time
        print(f"[Node.js Builder] ✓ Applied {len(task_runs)} task(s) in {output_dir}")
        return {
            "nodejs_output": {
                "status": "success",
                "output_dir": str(output_dir),
                "files_created": files_created,
                "artifact_paths": [str(output_dir / path) for path in files_created],
                "framework": "Express.js",
                "file_count": len(files_created),
                "task_runs": task_runs,
                "patches": [patch for run in task_runs for patch in run["patches"]],
                "observability": observability,
            },
            "nodejs_build_time": build_time,
        }
    except Exception as exc:
        if current_task is not None and current_task_clock is not None:
            try:
                record_generation_task_event(
                    state,
                    stack="nodejs",
                    event_type="task_finished",
                    task=current_task,
                    attempt=1,
                    started_at=current_task_started,
                    duration_ms=round((time.perf_counter() - current_task_clock) * 1000, 2),
                    status="failed",
                    input_artifacts=current_input_artifacts,
                    observability=current_usage,
                    error=exc,
                )
            except Exception:
                pass
        build_time = time.time() - start_time
        error_msg = f"Node.js builder failed: {exc}"
        print(f"[Node.js Builder] ✗ Error: {error_msg}")
        return {
            "nodejs_output": {
                "status": "failed",
                "error": str(exc),
                "output_dir": str(output_dir) if output_dir else None,
                "task_runs": task_runs,
                "patches": [patch for run in task_runs for patch in run["patches"]],
                "observability": observability,
            },
            "nodejs_build_time": build_time,
            "errors": [error_msg],
        }
