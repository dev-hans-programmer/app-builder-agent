"""
Python/FastAPI builder agent.

This module implements the Python builder that uses the OpenAI API to generate
complete FastAPI applications from user prompts.
"""

import os
import time
import re
from pathlib import Path
from src.graph.state import BuilderState
from src.graph.runtime import ensure_workspace_layout
from src.prompts.python_builder_prompt import create_python_prompt
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
    pattern = r'```filename:\s*(.+?)\n(.*?)```'

    # Find all matches (DOTALL allows . to match newlines)
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        filepath = match.group(1).strip()
        file_content = match.group(2).strip()

        # Only add non-empty files
        if filepath and file_content:
            files[filepath] = file_content

    return files


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
    # Create output directory
    base_path = Path(output_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    # Write each file
    for filepath, content in files.items():
        full_path = base_path / filepath

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file with UTF-8 encoding
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)


def build(state: BuilderState) -> dict:
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

    try:
        manifest = state.get("artifacts") or ensure_workspace_layout(
            ".",
            project_name=state.get("project_name"),
        )
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[Python Builder] ⚠️  OPENAI_API_KEY not found; using offline placeholder output")
            build_time = time.time() - start_time
            return {
                "python_output": {
                    "status": "placeholder",
                    "message": "OPENAI_API_KEY not found; skipping model call",
                    "output_dir": None,
                    "files_created": [],
                    "framework": "FastAPI",
                    "file_count": 0,
                },
                "python_build_time": build_time,
            }

        # Create OpenAI client
        client = OpenAI(api_key=api_key)

        # Create prompt
        prompt = create_python_prompt(
            state["user_prompt"],
            state["project_name"]
        )

        print(f"[Python Builder] Generating code for: {state['project_name']}")

        # Call OpenAI API
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extract text from response
        content = extract_response_text(response)

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
                "framework": "FastAPI",
                "file_count": len(files)
            },
            "python_build_time": build_time
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
                "error": str(e)
            },
            "python_build_time": build_time,
            "errors": state.get("errors", []) + [error_msg]
        }
