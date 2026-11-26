# Spec 002: State Management

## Overview
Define the LangGraph state schema that will be shared across all workflow nodes in the agent system.

## Scope

### In Scope
- BuilderState TypedDict definition
- State field documentation
- State initialization helper
- Basic state validation

### Out of Scope
- Actual workflow implementation (Spec 003)
- Agent logic (Specs 004-006)
- State persistence (future enhancement)

## Requirements

### 1. State Schema (src/graph/state.py)

```python
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime

class BuilderState(TypedDict):
    """
    Shared state across all workflow nodes.

    This state is passed between nodes and updated as the workflow progresses.
    Each node can read from and write to this state.
    """

    # User Input
    user_prompt: str              # Original user request
    project_name: str             # Sanitized project name (lowercase, hyphenated)

    # Python Builder Output
    python_output: Optional[Dict[str, Any]]
    # Structure:
    # {
    #     "status": "success" | "failed",
    #     "output_dir": str,
    #     "files_created": List[str],
    #     "framework": "FastAPI",
    #     "error": Optional[str]
    # }

    # Node.js Builder Output
    nodejs_output: Optional[Dict[str, Any]]
    # Structure:
    # {
    #     "status": "success" | "failed",
    #     "output_dir": str,
    #     "files_created": List[str],
    #     "framework": "Express",
    #     "error": Optional[str]
    # }

    # Comparison Output
    comparison_report: Optional[str]  # Markdown formatted report

    # Metadata
    timestamp: str                    # ISO format: YYYY-MM-DDTHH:MM:SS
    errors: List[str]                 # All errors encountered
    python_build_time: Optional[float]  # Seconds
    nodejs_build_time: Optional[float]  # Seconds
```

### 2. State Initialization Helper (src/graph/state.py)

```python
def create_initial_state(user_prompt: str, project_name: str) -> BuilderState:
    """
    Create initial state with user input and default values.

    Args:
        user_prompt: User's description of the app to build
        project_name: Project name (will be sanitized)

    Returns:
        BuilderState with initialized values
    """
    # Sanitize project name
    sanitized_name = sanitize_project_name(project_name)

    return BuilderState(
        user_prompt=user_prompt,
        project_name=sanitized_name,
        python_output=None,
        nodejs_output=None,
        comparison_report=None,
        timestamp=datetime.now().isoformat(),
        errors=[],
        python_build_time=None,
        nodejs_build_time=None,
    )

def sanitize_project_name(name: str) -> str:
    """
    Sanitize project name to be filesystem-safe.

    - Convert to lowercase
    - Replace spaces with hyphens
    - Remove special characters
    - Limit length to 50 characters

    Args:
        name: Raw project name

    Returns:
        Sanitized project name
    """
    import re

    # Convert to lowercase
    name = name.lower()

    # Replace spaces with hyphens
    name = name.replace(" ", "-")

    # Remove special characters (keep alphanumeric and hyphens)
    name = re.sub(r'[^a-z0-9-]', '', name)

    # Remove consecutive hyphens
    name = re.sub(r'-+', '-', name)

    # Remove leading/trailing hyphens
    name = name.strip("-")

    # Limit length
    name = name[:50]

    # Fallback if empty
    if not name:
        name = "untitled-project"

    return name
```

### 3. State Validation (src/graph/state.py)

```python
def validate_state(state: BuilderState) -> List[str]:
    """
    Validate state and return list of validation errors.

    Args:
        state: State to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Required fields
    if not state.get("user_prompt"):
        errors.append("user_prompt is required")

    if not state.get("project_name"):
        errors.append("project_name is required")

    # Validate project name format
    if state.get("project_name"):
        if not re.match(r'^[a-z0-9-]+$', state["project_name"]):
            errors.append("project_name must be lowercase alphanumeric with hyphens")

    # Validate timestamp format
    if state.get("timestamp"):
        try:
            datetime.fromisoformat(state["timestamp"])
        except ValueError:
            errors.append("timestamp must be in ISO format")

    return errors
```

## Success Criteria

- ✅ BuilderState TypedDict is properly defined
- ✅ All fields have type annotations
- ✅ create_initial_state() function works correctly
- ✅ sanitize_project_name() handles edge cases:
  - Spaces → hyphens
  - Special characters removed
  - Empty names → "untitled-project"
  - Long names truncated to 50 chars
- ✅ validate_state() catches invalid states
- ✅ All functions have docstrings
- ✅ Type hints are correct

## Testing

### Unit Tests (tests/test_state.py)

```python
def test_create_initial_state():
    """Test state initialization"""
    state = create_initial_state("Build a todo API", "My Project")
    assert state["user_prompt"] == "Build a todo API"
    assert state["project_name"] == "my-project"
    assert state["python_output"] is None
    assert state["nodejs_output"] is None
    assert isinstance(state["errors"], list)
    assert len(state["errors"]) == 0

def test_sanitize_project_name():
    """Test project name sanitization"""
    assert sanitize_project_name("My Cool Project") == "my-cool-project"
    assert sanitize_project_name("Test@#$App!") == "testapp"
    assert sanitize_project_name("   spaces   ") == "spaces"
    assert sanitize_project_name("Multiple---Hyphens") == "multiple-hyphens"
    assert sanitize_project_name("") == "untitled-project"
    assert len(sanitize_project_name("a" * 100)) <= 50

def test_validate_state():
    """Test state validation"""
    valid_state = create_initial_state("Test", "test-project")
    errors = validate_state(valid_state)
    assert len(errors) == 0

    invalid_state = BuilderState(
        user_prompt="",
        project_name="Invalid Name!",
        # ... other fields
    )
    errors = validate_state(invalid_state)
    assert len(errors) > 0
```

## Dependencies

- **Spec 001**: Project setup must be complete

---

**Status**: Ready for Implementation
**Estimated Time**: 20-25 minutes
