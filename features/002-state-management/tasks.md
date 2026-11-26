# Tasks 002: State Management

## Task List

### 1. Create State Module File
**Status**: Completed
**Time**: 2 min

Create `src/graph/state.py` with:
- Imports for TypedDict, Optional, Dict, Any, List
- Import datetime and re modules
- Module docstring

**Acceptance Criteria**:
- File exists at correct path
- All necessary imports present
- Module docstring describes purpose

---

### 2. Define BuilderState TypedDict
**Status**: Completed
**Time**: 8 min

Define `BuilderState` with all required fields:
- user_prompt: str
- project_name: str
- python_output: Optional[Dict[str, Any]]
- nodejs_output: Optional[Dict[str, Any]]
- comparison_report: Optional[str]
- timestamp: str
- errors: List[str]
- python_build_time: Optional[float]
- nodejs_build_time: Optional[float]

Include comprehensive docstring explaining:
- Purpose of each field
- Expected structure of dictionary fields
- When fields are populated

**Acceptance Criteria**:
- All fields have correct type annotations
- Docstring explains each field
- TypedDict can be imported and used

---

### 3. Implement sanitize_project_name()
**Status**: Completed
**Time**: 5 min

Create function that:
- Converts to lowercase
- Replaces spaces with hyphens
- Removes special characters
- Removes consecutive hyphens
- Strips leading/trailing hyphens
- Limits length to 50 characters
- Returns "untitled-project" for empty results

**Acceptance Criteria**:
- Handles all edge cases
- Returns filesystem-safe names
- Has comprehensive docstring
- Examples in docstring

---

### 4. Implement create_initial_state()
**Status**: Completed
**Time**: 5 min

Create function that:
- Takes user_prompt and project_name as parameters
- Sanitizes project_name
- Returns BuilderState with:
  - Input fields populated
  - Optional fields set to None
  - errors as empty list
  - timestamp as ISO format
  - build times as None

**Acceptance Criteria**:
- Function signature matches spec
- All state fields initialized correctly
- Timestamp is in ISO format
- Project name is sanitized
- Has docstring with args and returns

---

### 5. Implement validate_state()
**Status**: Completed
**Time**: 5 min

Create function that:
- Checks user_prompt is not empty
- Checks project_name is not empty
- Validates project_name format (lowercase, alphanumeric, hyphens only)
- Validates timestamp format (ISO 8601)
- Returns list of error messages

**Acceptance Criteria**:
- Returns empty list for valid state
- Returns error messages for invalid state
- Each validation check is clear
- Has docstring

---

### 6. Update __init__.py
**Status**: Completed
**Time**: 2 min

Update `src/graph/__init__.py` to export:
- BuilderState
- create_initial_state
- sanitize_project_name
- validate_state

**Acceptance Criteria**:
- All exports listed in __all__
- Functions can be imported from src.graph
- No import errors

---

### 7. Write Unit Tests
**Status**: Completed
**Time**: 10 min

Create `tests/test_state.py` with tests for:

**test_sanitize_project_name**:
- Normal names with spaces
- Special characters
- Empty strings
- Very long names (>50 chars)
- Multiple consecutive hyphens/spaces

**test_create_initial_state**:
- Creates state with correct structure
- Sanitizes project name
- Initializes all fields
- Sets timestamp in ISO format
- Empty errors list

**test_validate_state**:
- Valid state returns no errors
- Missing user_prompt caught
- Missing project_name caught
- Invalid project_name format caught
- Invalid timestamp format caught

**Acceptance Criteria**:
- All test functions pass
- Edge cases covered
- Tests are clear and readable
- pytest runs successfully

---

### 8. Run Tests and Validate
**Status**: Completed
**Time**: 3 min

Run tests and verify:
```bash
pytest tests/test_state.py -v
```

Manual validation in Python REPL:
```python
from src.graph.state import create_initial_state, sanitize_project_name

# Test examples
print(sanitize_project_name("My Cool App!"))
state = create_initial_state("Build API", "Test Project")
print(state)
```

**Acceptance Criteria**:
- All tests pass
- Manual validation works
- No import errors
- State structure is correct

---

## Summary

**Total Tasks**: 8
**Estimated Time**: 40 minutes
**Dependencies**: Spec 001 complete

## Checklist

- [x] 1. Create state module file
- [x] 2. Define BuilderState TypedDict
- [x] 3. Implement sanitize_project_name()
- [x] 4. Implement create_initial_state()
- [x] 5. Implement validate_state()
- [x] 6. Update __init__.py exports
- [x] 7. Write unit tests
- [x] 8. Run tests and validate

---

**Status**: Ready to Start
