"""
Prompt template for comparison agent.

This module contains the system prompt and helper functions for generating
prompts to Claude API for comparing Python and Node.js implementations.
"""

COMPARISON_PROMPT_VERSION = "1.0"


COMPARISON_SYSTEM_PROMPT = """You are an expert software architect with deep knowledge of both Python (FastAPI) and Node.js (Express) backend development.

Your task is to analyze and compare two backend implementations of the same application - one in Python/FastAPI and one in Node.js/Express.

Provide an objective, balanced comparison that helps developers choose the right stack for their needs.

Generate a comprehensive markdown report with the following sections:

# Executive Summary
- Brief overview (2-3 sentences)
- Key finding or recommendation upfront

# Build Status
(This will be added automatically)

# Implementation Overview

## Python Implementation
- Architecture and structure
- Key files and their purpose
- Notable patterns used

## Node.js Implementation
- Architecture and structure
- Key files and their purpose
- Notable patterns used

# Detailed Comparison

## Code Quality
| Aspect | Python (FastAPI) | Node.js (Express) | Winner |
|--------|------------------|-------------------|---------|
| Type Safety | ... | ... | ... |
| Error Handling | ... | ... | ... |
| Code Organization | ... | ... | ... |
| Documentation | ... | ... | ... |

## Performance Considerations
- Async/await patterns
- Database interactions
- API response handling
- Scalability approach

## Developer Experience
- Learning curve
- Tooling and ecosystem
- Debugging capabilities
- Development speed

## Production Readiness
- Error handling robustness
- Logging and monitoring
- Configuration management
- Security practices

# Strengths and Weaknesses

## Python/FastAPI Strengths
- ...

## Python/FastAPI Weaknesses
- ...

## Node.js/Express Strengths
- ...

## Node.js/Express Weaknesses
- ...

# Recommendation

Provide a clear, justified recommendation for:
- When to choose Python/FastAPI
- When to choose Node.js/Express
- Factors that influenced the recommendation

# Conclusion
- Final thoughts
- Next steps for the developer

---

**IMPORTANT:**
- Be objective and balanced
- Back claims with specific examples from the generated code
- Consider the user's original requirements
- Focus on practical, actionable insights
- Use the comparison table format shown above
"""


def create_comparison_prompt(
    user_prompt: str, python_output: dict, nodejs_output: dict
) -> str:
    """
    Create the full prompt for comparison agent.

    Combines the system prompt with build information to create a complete
    prompt for Claude API to analyze and compare both implementations.

    Args:
        user_prompt: User's original request
        python_output: Python builder output dict with status, files, etc.
        nodejs_output: Node.js builder output dict with status, files, etc.

    Returns:
        Complete prompt string ready for Claude API

    Example:
        >>> prompt = create_comparison_prompt(
        ...     "Build a todo API",
        ...     {"status": "success", "file_count": 10},
        ...     {"status": "success", "file_count": 8}
        ... )
        >>> "todo API" in prompt
        True
        >>> "FastAPI" in prompt
        True
    """
    # Extract build information
    python_status = python_output.get("status", "unknown")
    python_files = python_output.get("file_count", 0)
    python_dir = python_output.get("output_dir", "N/A")
    python_file_list = python_output.get("files_created", [])

    nodejs_status = nodejs_output.get("status", "unknown")
    nodejs_files = nodejs_output.get("file_count", 0)
    nodejs_dir = nodejs_output.get("output_dir", "N/A")
    nodejs_file_list = nodejs_output.get("files_created", [])

    # Format file lists
    python_files_formatted = (
        "\n".join(f"  - {f}" for f in python_file_list)
        if python_file_list
        else "  (No files)"
    )
    nodejs_files_formatted = (
        "\n".join(f"  - {f}" for f in nodejs_file_list)
        if nodejs_file_list
        else "  (No files)"
    )

    return f"""{COMPARISON_SYSTEM_PROMPT}

## User's Original Request
"{user_prompt}"

## Build Information

### Python (FastAPI) Build
- Status: {python_status}
- Files Created: {python_files}
- Output Directory: {python_dir}
- File List:
{python_files_formatted}

### Node.js (Express) Build
- Status: {nodejs_status}
- Files Created: {nodejs_files}
- Output Directory: {nodejs_dir}
- File List:
{nodejs_files_formatted}

---

Based on the user's requirements and the build information above, generate a comprehensive comparison report.
Focus on helping the developer choose the right stack for their specific needs.
"""
