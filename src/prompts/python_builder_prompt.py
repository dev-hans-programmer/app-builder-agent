"""
Prompt template for Python/FastAPI builder agent.

This module contains the system prompt and helper functions for generating
prompts to Claude API for Python backend code generation.
"""

PYTHON_BUILDER_SYSTEM_PROMPT = """You are an expert Python backend developer specializing in FastAPI.

Your task is to generate a complete, production-ready FastAPI application based on the user's requirements.

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
"""


def create_python_prompt(user_prompt: str, project_name: str) -> str:
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
    return f"""{PYTHON_BUILDER_SYSTEM_PROMPT}

Project Name: {project_name}
User Request: {user_prompt}

Generate a complete FastAPI application that fulfills this request.
"""
