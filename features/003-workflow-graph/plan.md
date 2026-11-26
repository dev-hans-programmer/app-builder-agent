# Plan 003: LangGraph Workflow

## Implementation Approach

### Phase 1: Node Functions (10 min)
1. Create `src/graph/workflow.py`
2. Implement `parse_input_node()`
3. Implement `generate_report_node()`
4. Create placeholder functions for builders and comparison

### Phase 2: Workflow Definition (10 min)
1. Import StateGraph and END from langgraph
2. Create `create_workflow()` function
3. Add all nodes to graph
4. Define edges (including parallel execution)
5. Set entry point
6. Compile workflow

### Phase 3: Integration (10 min)
1. Update `src/graph/__init__.py` exports
2. Update `main.py` to use workflow
3. Test workflow execution

### Phase 4: Testing (10 min)
1. Create `tests/test_workflow.py`
2. Test workflow creation
3. Test end-to-end execution
4. Test report generation
5. Verify parallel execution works

## Key Decisions

1. **Parallel Execution**: Use LangGraph's built-in parallelization by having multiple edges from same source node
2. **Placeholders**: Create placeholder functions for unimplemented agents to allow testing
3. **Report Storage**: Save to `./reports/` with timestamped filename
4. **Error Collection**: Errors collected in state, don't block workflow
5. **Entry Point**: `parse_input` validates before any processing

## Implementation Order

1. ✅ Create placeholder functions (testable stubs)
2. ✅ Implement `parse_input_node()` (validation logic)
3. ✅ Implement `generate_report_node()` (file I/O)
4. ✅ Create workflow graph structure
5. ✅ Add nodes and edges
6. ✅ Compile workflow
7. ✅ Update main.py to test
8. ✅ Write tests

## LangGraph Parallel Execution

LangGraph automatically executes nodes in parallel when multiple edges originate from the same source node:

```python
# This creates parallel execution:
workflow.add_edge("parse_input", "python_builder")
workflow.add_edge("parse_input", "nodejs_builder")

# Both builders run simultaneously
# The next node (comparison) waits for BOTH to complete
workflow.add_edge("python_builder", "comparison")
workflow.add_edge("nodejs_builder", "comparison")
```

## Workflow Visualization

```
START
  ↓
parse_input (validates input)
  ↓
  ├─→ python_builder (parallel)
  └─→ nodejs_builder (parallel)
  ↓
comparison (waits for both)
  ↓
generate_report (saves to disk)
  ↓
END
```

## Edge Cases to Handle

### In parse_input_node
- Empty user prompt → Add to errors
- Empty project name → Add to errors
- Invalid characters in project name → Already sanitized in state creation

### In generate_report_node
- Missing reports directory → Create it
- No comparison report → Skip writing
- Invalid filename characters → Sanitize timestamp

## File Structure After This Spec

```
src/graph/
├── __init__.py       # Exports state + workflow
├── state.py          # (from Spec 002)
└── workflow.py       # NEW: Workflow definition
```

## Testing Strategy

### Unit Tests
- Test each node function independently
- Test workflow creation
- Test edge definitions

### Integration Tests
- Test full workflow execution
- Test parallel execution timing
- Test report file creation

### Manual Tests
- Run `python main.py`
- Verify placeholder messages
- Check report file created in ./reports/

## Validation Commands

```bash
# Test workflow creation
python -c "from src.graph.workflow import create_workflow; w = create_workflow(); print('OK')"

# Run full workflow
python main.py

# Check report created
ls -la reports/

# Run tests
pytest tests/test_workflow.py -v
```

## Potential Issues

1. **Import Errors**: Make sure langgraph is installed
2. **Circular Dependencies**: Avoid importing agents in workflow.py (use placeholders)
3. **File Permissions**: Ensure ./reports/ directory is writable
4. **Parallel Execution**: LangGraph handles this automatically, no special code needed

---

**Time Estimate**: 35-40 minutes
**Dependencies**: Spec 001, 002
**Risk**: Low (using placeholders for unimplemented components)
