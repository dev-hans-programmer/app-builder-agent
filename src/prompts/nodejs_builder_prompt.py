"""
Prompt template for Node.js/Express builder agent.

This module contains the system prompt and helper functions for generating
prompts to Claude API for Node.js backend code generation.
"""

NODEJS_BUILDER_PROMPT_VERSION = "1.0"


NODEJS_BUILDER_SYSTEM_PROMPT = """You are an expert Node.js backend developer specializing in Express.js.

Your task is to generate a complete, production-ready Express.js application based on the user's requirements.

IMPORTANT: Output each file using this exact format:
```filename: path/to/file.js
[file contents here]
```

Requirements:
1. Use Express.js framework
2. Use modern JavaScript (ES6+) with async/await
3. Use ES modules (type: "module" in package.json)
4. Include proper error handling with try-catch
5. Use middleware appropriately
6. Include a package.json file with all dependencies
7. Include a README.md with setup instructions
8. Structure code properly (separate routes, controllers, middleware)
9. Add JSDoc comments to functions
10. Use meaningful variable names
11. Follow Node.js best practices
12. Use proper HTTP status codes

Start with package.json, then server.js or app.js, then other files as needed.
Keep the code clean, simple, and well-organized.
"""


def create_nodejs_prompt(user_prompt: str, project_name: str) -> str:
    """
    Create the full prompt for Node.js/Express builder.

    Combines the system prompt with the user's specific request and project name
    to create a complete prompt for Claude API.

    Args:
        user_prompt: User's description of the app to build
        project_name: Sanitized project name

    Returns:
        Complete prompt string ready for Claude API

    Example:
        >>> prompt = create_nodejs_prompt(
        ...     "Build a todo API",
        ...     "todo-api"
        ... )
        >>> "Express" in prompt
        True
        >>> "todo-api" in prompt
        True
    """
    return f"""{NODEJS_BUILDER_SYSTEM_PROMPT}

Project Name: {project_name}
User Request: {user_prompt}

Generate a complete Express.js application that fulfills this request.
"""
