"""
Prompt template for Python/FastAPI builder agent.

This module contains the system prompt and helper functions for generating
prompts to Claude API for Python backend code generation.
"""

import json


PYTHON_BUILDER_PROMPT_VERSION = "2.0"


PYTHON_BUILDER_SYSTEM_PROMPT = """You are an expert Python backend developer specializing in FastAPI.

Your task is to implement one executable task in a production-ready FastAPI application.

IMPORTANT: Output each file using this exact format:
```filename: path/to/file.py
[file contents here]
```

Requirements:
1. Use FastAPI framework
2. Follow Python best practices (PEP 8)
3. Include type hints throughout
4. Use Pydantic models for request/response validation
5. Proper error handling with try-except blocks
6. Include a requirements.txt file
7. Include a README.md with setup instructions
8. Structure code properly (separate routes, models, config)
9. Add docstrings to functions
10. Use meaningful variable names

Start with requirements.txt, then main.py, then other files as needed.
Keep the code clean, simple, and well-organized.

For task-level generation:
- Treat approved acceptance criteria and architecture contracts as binding.
- Output only files created or changed by the current task.
- Always output complete file contents, never diffs or placeholders.
- Preserve compatible behavior from the supplied current files.
- Add or update focused automated tests for the task.
"""


def create_python_prompt(
    user_prompt: str,
    project_name: str,
    *,
    task: dict | None = None,
    requirements: dict | None = None,
    architecture: dict | None = None,
    current_files: dict[str, str] | None = None,
) -> str:
    """
    Create the full prompt for Python/FastAPI builder.

    Combines the system prompt with the user's specific request and project name
    to create a complete prompt for Claude API.

    Args:
        user_prompt: User's description of the app to build
        project_name: Sanitized project name

    Returns:
        Complete prompt string ready for Claude API

    Example:
        >>> prompt = create_python_prompt(
        ...     "Build a todo API",
        ...     "todo-api"
        ... )
        >>> "FastAPI" in prompt
        True
        >>> "todo-api" in prompt
        True
    """
    context = ""
    if task is not None:
        context = f"""
Approved requirements and acceptance criteria:
{json.dumps(requirements or {}, indent=2, sort_keys=True)}

Architecture and contracts:
{json.dumps(architecture or {}, indent=2, sort_keys=True)}

Current executable task:
{json.dumps(task, indent=2, sort_keys=True)}

Current project files:
{json.dumps(current_files or {}, indent=2, sort_keys=True)}
"""
    return f"""{PYTHON_BUILDER_SYSTEM_PROMPT}

Project Name: {project_name}
User Request: {user_prompt}
{context}

Implement the current task. If no task context is present: Generate a complete FastAPI application.
"""
