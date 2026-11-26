# Tasks 004: Python Builder Agent

## Task List

### 1. Create Prompt Template Module
**Status**: Completed
**Time**: 10 min

Create `src/prompts/python_builder_prompt.py` with:
- `PYTHON_BUILDER_SYSTEM_PROMPT` constant
- `create_python_prompt(user_prompt, project_name)` function
- Clear instructions for file format
- Python/FastAPI specific requirements

**Acceptance Criteria**:
- System prompt is comprehensive
- Output format clearly specified
- Function combines system prompt with user input
- Has docstrings

---

### 2. Implement parse_code_blocks()
**Status**: Completed
**Time**: 12 min

In `src/agents/python_builder.py`, implement function that:
- Uses regex to find ```filename: path\n[content]``` blocks
- Extracts filepath and content
- Returns dict mapping paths to contents
- Handles multiple code blocks
- Skips blocks without filename marker

**Acceptance Criteria**:
- Regex pattern works correctly
- Returns dictionary of files
- Handles edge cases (no files, malformed blocks)
- Has docstring with examples

---

### 3. Implement write_files()
**Status**: Completed
**Time**: 8 min

Implement function that:
- Creates output directory if needed
- Iterates through files dict
- Creates parent directories for nested paths
- Writes each file with UTF-8 encoding

**Acceptance Criteria**:
- Creates directories recursively
- Writes files correctly
- Handles nested paths (e.g., "api/routes/users.py")
- Has docstring

---

### 4. Implement build() Function
**Status**: Completed
**Time**: 20 min

Create main builder function that:
- Gets API key from environment
- Creates Anthropic client
- Creates prompt using template
- Calls Claude API with appropriate parameters
- Parses response
- Writes files to ./builds/python-{project}/
- Updates state with results
- Tracks build time
- Handles errors gracefully

**Acceptance Criteria**:
- API integration works
- Error handling is comprehensive
- State updated correctly on success/failure
- Print statements for visibility
- Has detailed docstring

---

### 5. Update Workflow Integration
**Status**: Completed
**Time**: 5 min

Update `src/graph/workflow.py`:
- Import python_builder.build
- Replace `python_builder_placeholder` with actual function
- Remove or comment out placeholder

**Acceptance Criteria**:
- Import works
- Workflow uses real builder
- No import errors

---

### 6. Update Environment Configuration
**Status**: Completed
**Time**: 3 min

Ensure `.env` has:
- `ANTHROPIC_API_KEY` (actual key)
- `CLAUDE_MODEL` (with default)

Update `.env.example` if needed.

**Acceptance Criteria**:
- API key is set
- Model name is correct
- .env.example updated

---

### 7. Write Unit Tests
**Status**: Completed
**Time**: 15 min

Create `tests/test_python_builder.py` with:

**test_parse_code_blocks**:
- Single file
- Multiple files
- No files (empty response)
- Malformed blocks

**test_write_files**:
- Flat file structure
- Nested directories
- File content correctness
- (use tmp_path fixture)

**test_create_python_prompt**:
- Prompt includes user request
- Prompt includes project name
- System prompt included

**Acceptance Criteria**:
- All tests pass
- Edge cases covered
- Uses pytest fixtures appropriately

---

### 8. Integration Test (Optional)
**Status**: Pending
**Time**: 10 min

Create integration test with mocked API:
- Mock Anthropic client
- Mock response with sample code
- Test full build() function flow
- Verify state updates

**Acceptance Criteria**:
- Test doesn't require real API key
- Full flow tested
- Both success and failure paths covered

---

### 9. Manual Testing with Real API
**Status**: Completed
**Time**: 10 min

Run with actual Claude API:
```bash
# Set API key
export ANTHROPIC_API_KEY="your_key"

# Run workflow
python main.py
# Input: "Build a simple todo API with CRUD operations"
# Project name: "todo-api"

# Verify output
ls -la builds/python-todo-api/
cat builds/python-todo-api/main.py
cat builds/python-todo-api/requirements.txt
cat builds/python-todo-api/README.md

# Try installing (optional)
cd builds/python-todo-api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Acceptance Criteria**:
- Code generates successfully
- Files are created
- Code is syntactically valid
- requirements.txt is complete
- README has instructions

---

### 10. Handle Common Issues
**Status**: Completed
**Time**: 5 min

Test and fix:
- Missing API key → Clear error message
- API rate limit → Error handled gracefully
- No files parsed → Clear error
- File write errors → Appropriate error

**Acceptance Criteria**:
- All error conditions handled
- Error messages are helpful
- State errors populated
- No uncaught exceptions

---

## Summary

**Total Tasks**: 10
**Estimated Time**: ~90 minutes (including testing with real API)
**Dependencies**: Spec 001-003 complete, ANTHROPIC_API_KEY available

## Checklist

- [x] 1. Create prompt template module
- [x] 2. Implement parse_code_blocks()
- [x] 3. Implement write_files()
- [x] 4. Implement build() function
- [x] 5. Update workflow integration
- [x] 6. Update environment configuration
- [x] 7. Write unit tests
- [ ] 8. Integration test (optional)
- [x] 9. Manual testing with real API
- [x] 10. Handle common issues

---

**Status**: Ready to Start
**Note**: Requires valid ANTHROPIC_API_KEY for full testing
