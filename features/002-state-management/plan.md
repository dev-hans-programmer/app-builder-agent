# Plan 002: State Management

## Implementation Approach

### Phase 1: Define State Schema (8 min)
1. Create `src/graph/state.py`
2. Import required types (TypedDict, Optional, etc.)
3. Define BuilderState with all fields
4. Add comprehensive docstrings

### Phase 2: State Initialization (7 min)
1. Implement `sanitize_project_name()` function
2. Implement `create_initial_state()` function
3. Test with various project names

### Phase 3: State Validation (5 min)
1. Implement `validate_state()` function
2. Add validation rules for required fields
3. Add format validation (project name, timestamp)

### Phase 4: Testing (10 min)
1. Create `tests/test_state.py`
2. Write unit tests for sanitize_project_name()
3. Write unit tests for create_initial_state()
4. Write unit tests for validate_state()
5. Run tests: `pytest tests/test_state.py -v`

## Key Decisions

1. **State Structure**: Using TypedDict for type safety and IDE support
2. **Immutability**: State is updated by returning new state (LangGraph pattern)
3. **Error Handling**: Collect all errors in a list rather than raising exceptions
4. **Project Name Sanitization**: Lowercase + hyphens for filesystem compatibility
5. **Timestamp Format**: ISO 8601 for universal compatibility

## Implementation Order

1. ✅ Define BuilderState TypedDict (foundation)
2. ✅ Implement sanitize_project_name() (dependency for initialization)
3. ✅ Implement create_initial_state() (uses sanitization)
4. ✅ Implement validate_state() (quality check)
5. ✅ Write tests (validation)

## Edge Cases to Handle

### Project Name Sanitization
- Empty string → "untitled-project"
- Only special characters → "untitled-project"
- Very long names → Truncate to 50 chars
- Multiple consecutive spaces/hyphens → Single hyphen
- Leading/trailing hyphens → Remove

### State Validation
- Missing required fields
- Invalid timestamp format
- Invalid project name format
- None values where not expected

## Code Structure

```
src/graph/
├── __init__.py          # Export BuilderState, create_initial_state
└── state.py             # State definition and utilities
```

### Imports in src/graph/__init__.py
```python
from src.graph.state import (
    BuilderState,
    create_initial_state,
    sanitize_project_name,
    validate_state,
)

__all__ = [
    "BuilderState",
    "create_initial_state",
    "sanitize_project_name",
    "validate_state",
]
```

## Testing Strategy

### Test Categories
1. **Happy Path**: Valid inputs produce valid state
2. **Edge Cases**: Empty strings, special characters, long names
3. **Validation**: Invalid states are caught

### Test Commands
```bash
# Run all state tests
pytest tests/test_state.py -v

# Run with coverage
pytest tests/test_state.py --cov=src.graph.state

# Run specific test
pytest tests/test_state.py::test_sanitize_project_name -v
```

## Potential Issues

1. **Regex Import**: Need to import `re` module for sanitization
2. **DateTime Import**: Need `datetime` from standard library
3. **Type Checking**: TypedDict is runtime-checked, may need mypy for strict checking

## Validation Steps

```python
# Quick validation in Python REPL
from src.graph.state import create_initial_state, sanitize_project_name

# Test sanitization
print(sanitize_project_name("My Cool App"))  # Should: my-cool-app

# Test state creation
state = create_initial_state("Build a todo API", "Test Project")
print(state["project_name"])  # Should: test-project
print(state["timestamp"])     # Should: ISO format
print(len(state["errors"]))   # Should: 0
```

---

**Time Estimate**: 25-30 minutes
**Dependencies**: Spec 001 (Project Setup)
**Risk**: Low
