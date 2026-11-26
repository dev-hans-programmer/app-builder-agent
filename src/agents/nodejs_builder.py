"""
Node.js/Express builder agent.

This module implements the Node.js builder that uses the OpenAI API to generate
complete Express.js applications from user prompts.
"""

import os
import time
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
    extract_response_text,
    parse_code_blocks,
    write_files,
)
from openai import OpenAI


def build(state: BuilderState) -> dict:
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
