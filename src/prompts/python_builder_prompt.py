"""
Prompt template for Python/FastAPI builder agent.

This module contains the system prompt and helper functions for generating
prompts to Claude API for Python backend code generation.
"""

import json

from src.policy import policy_text_for_task

PYTHON_BUILDER_PROMPT_VERSION = "3.0"


PYTHON_BUILDER_SYSTEM_PROMPT = """You are a senior backend architect and Python engineer implementing one task in a production-grade FastAPI service.

Your task is to implement one executable task in a production-ready FastAPI application.

Return JSON only. Do not wrap it in Markdown. Use this exact envelope:
{
  "task_id": "the current task ID",
  "acceptance_criteria_ids": ["every acceptance criterion ID assigned to the task"],
  "policy_rule_ids": ["every policy rule ID assigned to the task"],
  "files": [
    {"path": "relative/path/to/file.py", "content": "complete file contents"}
  ]
}

The approved acceptance criteria, contracts, production architecture, and backend policy are binding.
Output only files created or changed by the current task. Always return complete file contents,
never diffs, ellipses, TODOs, mock implementations, or placeholder code. Preserve compatible
behavior from supplied current files and add focused tests alongside implementation. Echo the task's
acceptance criteria and policy rule IDs exactly so the result can be validated and traced.
"""


def create_python_prompt(
    user_prompt: str,
    project_name: str,
    *,
    task: dict | None = None,
    requirements: dict | None = None,
    architecture: dict | None = None,
    current_files: dict[str, str] | None = None,
    backend_policy: dict | None = None,
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
        policy = backend_policy or {}
        policy_text = (
            policy_text_for_task(
                policy, str(task.get("kind") or task.get("module") or "feature")
            )
            if policy.get("enabled")
            else "No Python production policy was loaded."
        )
        context = f"""
Binding Python production policy:
{policy_text}

Approved requirements and acceptance criteria:
{json.dumps(requirements or {}, indent=2, sort_keys=True)}

Architecture and contracts:
{json.dumps(architecture or {}, indent=2, sort_keys=True)}

Current executable task:
{json.dumps(task, indent=2, sort_keys=True)}

Current project files:
{json.dumps(current_files or {}, indent=2, sort_keys=True)}

Task execution rules:
- Modify only paths explicitly allowed by the task.
- Respect dependency direction and keep HTTP, application, domain, and infrastructure concerns separate.
- Implement contracts and tests tied to this task's acceptance and policy rule IDs.
- Do not regenerate unrelated files or replace working production code with a simplified version.
"""
    return f"""{PYTHON_BUILDER_SYSTEM_PROMPT}

Project Name: {project_name}
User Request: {user_prompt}
{context}

Implement the current task completely. If no task context is present: Generate a complete FastAPI application.
"""
