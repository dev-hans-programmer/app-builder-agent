# Plan 005: Node.js Builder Agent

## Implementation Approach

### Phase 1: Prompt Template (8 min)
1. Create `src/prompts/nodejs_builder_prompt.py`
2. Define system prompt for Express
3. Create `create_nodejs_prompt()` function
4. Test prompt generation

### Phase 2: Node.js Builder (15 min)
1. Create `src/agents/nodejs_builder.py`
2. Import parse_code_blocks and write_files from python_builder
3. Implement `build()` function (similar to Python builder)
4. Use nodejs-specific output directory and state fields

### Phase 3: Workflow Integration (3 min)
1. Import nodejs_builder.build in workflow.py
2. Replace placeholder with actual function

### Phase 4: Testing (12 min)
1. Create unit tests
2. Test prompt generation
3. Manual test with real API
4. Verify parallel execution

## Key Decisions

1. **Code Reuse**: Reuse `parse_code_blocks()` and `write_files()` from python_builder
   - Same format works for both languages
   - DRY principle

2. **Prompt Engineering**: Similar structure to Python prompt but Express-specific
   - Modern ES6+ syntax
   - Express middleware patterns
   - package.json instead of requirements.txt

3. **Output Directory**: `./builds/nodejs-{project-name}/`
   - Clear separation from Python builds
   - Consistent naming pattern

4. **Parallel Execution**: Already configured in workflow (Spec 003)
   - No special code needed
   - LangGraph handles it automatically

## Implementation Order

1. ✅ Create prompt template (foundation)
2. ✅ Implement builder (main logic, reuses utilities)
3. ✅ Integrate with workflow
4. ✅ Test

## Code Reuse Strategy

### From python_builder.py
```python
from src.agents.python_builder import (
    parse_code_blocks,  # Reuse: same format
    write_files,        # Reuse: language-agnostic
)
```

### New in nodejs_builder.py
```python
def build(state: BuilderState) -> BuilderState:
    # Similar structure to python_builder.build()
    # Different:
    # - Prompt template
    # - Output directory naming
    # - State field (nodejs_output)
```

## Prompt Engineering Differences

### Python Prompt Focus
- FastAPI specific
- Type hints
- Pydantic models
- requirements.txt

### Node.js Prompt Focus
- Express specific
- ES6+ syntax
- Middleware
- package.json
- async/await patterns

## Testing Strategy

### Unit Tests
1. Prompt generation
2. Mocked API response
3. State updates

### Integration Test
1. Run full workflow
2. Verify both builders execute
3. Check build times (should overlap, not sum)

### Manual Test
```bash
python main.py
# Input: "Build a REST API for books management"

# Check both directories created
ls builds/
# Should see: python-books-api/ and nodejs-books-api/

# Verify files
cat builds/nodejs-books-api/package.json
cat builds/nodejs-books-api/server.js
```

## Parallel Execution Verification

### Timing Test
```python
import time

start = time.time()
# Run workflow
workflow.invoke(state)
duration = time.time() - start

# If parallel: duration ≈ max(python_time, nodejs_time)
# If sequential: duration ≈ python_time + nodejs_time
```

Expected: Parallel execution, so duration should be close to the slower of the two, not their sum.

## Potential Issues

1. **Import Path**: Make sure to import from src.agents.python_builder correctly
2. **State Key**: Use "nodejs_output" not "python_output"
3. **Directory Naming**: Use "nodejs-" prefix, not "python-"
4. **Error Handling**: Both builders should work independently (one failure doesn't block the other)

## Validation Steps

```python
# Test prompt
from src.prompts.nodejs_builder_prompt import create_nodejs_prompt

prompt = create_nodejs_prompt("Build API", "test")
print(prompt)  # Should include Express, package.json, etc.

# Test builder (with mock)
from src.agents.nodejs_builder import build
from src.graph.state import create_initial_state

state = create_initial_state("Test", "test")
# Would need to mock API for real test
```

---

**Time Estimate**: 35-40 minutes
**Dependencies**: Spec 001-004
**Risk**: Low (reuses proven patterns from 004)
