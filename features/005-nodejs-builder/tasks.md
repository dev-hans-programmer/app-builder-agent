# Tasks 005: Node.js Builder Agent

## Task List

### 1. Create Prompt Template Module
**Status**: Completed
**Time**: 8 min

Create `src/prompts/nodejs_builder_prompt.py` with:
- `NODEJS_BUILDER_SYSTEM_PROMPT` constant
- Express/Node.js specific requirements
- Clear file format instructions
- `create_nodejs_prompt(user_prompt, project_name)` function

**Acceptance Criteria**:
- System prompt is comprehensive
- Mentions Express, ES6+, package.json
- Output format matches Python builder format
- Has docstrings

---

### 2. Implement Node.js Builder
**Status**: Completed
**Time**: 18 min

Create `src/agents/nodejs_builder.py`:
- Import parse_code_blocks and write_files from python_builder
- Implement `build(state)` function with:
  - API key validation
  - Anthropic client creation
  - Prompt generation
  - API call
  - Response parsing
  - File writing to ./builds/nodejs-{project}/
  - State update (nodejs_output)
  - Error handling
  - Build time tracking

**Acceptance Criteria**:
- Reuses utilities from python_builder
- Uses nodejs_output state field
- Output directory uses "nodejs-" prefix
- Error handling is comprehensive
- Has docstring

---

### 3. Update Workflow Integration
**Status**: Completed
**Time**: 3 min

Update `src/graph/workflow.py`:
- Import nodejs_builder.build
- Replace `nodejs_builder_placeholder` with actual function
- Remove or comment out placeholder

**Acceptance Criteria**:
- Import works
- Both builders are real (not placeholders)
- No import errors

---

### 4. Write Unit Tests
**Status**: Completed
**Time**: 10 min

Create `tests/test_nodejs_builder.py`:

**test_create_nodejs_prompt**:
- Prompt includes user request
- Prompt includes project name
- System prompt has Express requirements

**test_build_with_mock** (optional):
- Mock API call
- Verify state updates
- Test error handling

**Acceptance Criteria**:
- Tests pass
- Key functionality covered

---

### 5. Manual Testing with Real API
**Status**: Completed
**Time**: 12 min

Run full workflow:
```bash
# Run with both builders
python main.py
# Input: "Build a REST API for managing books with CRUD operations"
# Project: "books-api"

# Verify both directories exist
ls -la builds/
# Should see:
# - python-books-api/
# - nodejs-books-api/

# Check Node.js files
cat builds/nodejs-books-api/package.json
cat builds/nodejs-books-api/server.js
cat builds/nodejs-books-api/README.md

# Check Python files
cat builds/python-books-api/main.py
cat builds/python-books-api/requirements.txt

# Optional: Verify Node.js syntax
cd builds/nodejs-books-api
node --check server.js
```

**Acceptance Criteria**:
- Both builds succeed
- Both directories created
- Files are valid
- Code is syntactically correct

---

### 6. Verify Parallel Execution
**Status**: Completed
**Time**: 5 min

Add timing check to verify parallelism:
```python
# In main.py or test
import time

start = time.time()
final_state = workflow.invoke(state)
duration = time.time() - start

print(f"Total time: {duration:.2f}s")
print(f"Python time: {final_state['python_build_time']:.2f}s")
print(f"Node.js time: {final_state['nodejs_build_time']:.2f}s")

# If parallel: total ≈ max(python, nodejs)
# If sequential: total ≈ python + nodejs
```

**Acceptance Criteria**:
- Total time is close to slowest builder
- Total time is NOT sum of both builders
- Confirms parallel execution working

---

### 7. Test Error Scenarios
**Status**: Completed
**Time**: 5 min

Test error handling:
1. One builder fails, other succeeds
2. Both builders fail
3. API key missing
4. No files generated

**Acceptance Criteria**:
- Errors added to state
- One failure doesn't block the other
- Comparison still runs (even with partial results)

---

## Summary

**Total Tasks**: 7
**Estimated Time**: ~60 minutes (including real API testing)
**Dependencies**: Spec 001-004 complete

## Checklist

- [x] 1. Create prompt template module
- [x] 2. Implement Node.js builder
- [x] 3. Update workflow integration
- [x] 4. Write unit tests
- [x] 5. Manual testing with real API
- [x] 6. Verify parallel execution
- [x] 7. Test error scenarios

---

**Status**: Ready to Start
**Note**: Can be done in parallel with Spec 006 (Comparison Agent)
