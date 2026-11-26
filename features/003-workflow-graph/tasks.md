# Tasks 003: LangGraph Workflow

## Task List

### 1. Create Workflow Module
**Status**: Completed
**Time**: 2 min

Create `src/graph/workflow.py` with:
- Imports for StateGraph, END
- Import BuilderState from state module
- Module docstring

**Acceptance Criteria**:
- File exists
- Imports work
- No syntax errors

---

### 2. Implement parse_input_node()
**Status**: Completed
**Time**: 5 min

Create function that:
- Takes BuilderState as input
- Validates user_prompt exists
- Validates project_name exists
- Adds errors to state if invalid
- Returns updated state

**Acceptance Criteria**:
- Function signature correct
- Validation logic works
- Errors added to state["errors"]
- Has docstring

---

### 3. Implement generate_report_node()
**Status**: Completed
**Time**: 7 min

Create function that:
- Creates ./reports/ directory if missing
- Generates timestamped filename
- Writes comparison_report to file
- Returns state unchanged

**Acceptance Criteria**:
- Directory created if needed
- File written with correct content
- Filename uses timestamp
- Handles missing report gracefully
- Has docstring

---

### 4. Create Placeholder Functions
**Status**: Completed
**Time**: 5 min

Create three placeholder functions:
- `python_builder_placeholder()` - Sets placeholder python_output
- `nodejs_builder_placeholder()` - Sets placeholder nodejs_output
- `comparison_placeholder()` - Sets placeholder comparison_report

Each should:
- Print placeholder message
- Update appropriate state field
- Return state

**Acceptance Criteria**:
- All three functions defined
- Each updates correct state field
- Print messages for visibility
- Have docstrings noting they're placeholders

---

### 5. Implement create_workflow()
**Status**: Completed
**Time**: 12 min

Create function that:
- Creates StateGraph with BuilderState
- Adds all 5 nodes (parse_input, python_builder, nodejs_builder, comparison, generate_report)
- Sets "parse_input" as entry point
- Adds edges for parallel execution:
  - parse_input → python_builder
  - parse_input → nodejs_builder
  - python_builder → comparison
  - nodejs_builder → comparison
  - comparison → generate_report
  - generate_report → END
- Compiles and returns workflow

**Acceptance Criteria**:
- StateGraph created correctly
- All nodes added
- Edges create correct flow
- Parallel execution configured
- Workflow compiles without errors
- Has comprehensive docstring with diagram

---

### 6. Update Module Exports
**Status**: Completed
**Time**: 2 min

Update `src/graph/__init__.py` to export:
- create_workflow
- parse_input_node
- generate_report_node

**Acceptance Criteria**:
- Functions can be imported from src.graph
- __all__ list updated
- No import errors

---

### 7. Update main.py
**Status**: Completed
**Time**: 5 min

Update `main.py` to:
- Import create_initial_state and create_workflow
- Create sample initial state
- Create and invoke workflow
- Print results

**Acceptance Criteria**:
- Imports work
- Workflow executes
- Output is readable
- No errors

---

### 8. Write Tests
**Status**: Completed
**Time**: 10 min

Create `tests/test_workflow.py` with tests:

**test_parse_input_node**:
- Valid input passes
- Missing prompt adds error
- Missing project_name adds error

**test_generate_report_node**:
- Creates reports directory
- Writes file with correct content
- Filename format is correct

**test_create_workflow**:
- Workflow is created
- Returns compiled graph

**test_workflow_execution**:
- End-to-end test
- State flows through all nodes
- Final state has all outputs

**Acceptance Criteria**:
- All tests pass
- Coverage of key functionality
- Tests are clear and maintainable

---

### 9. Manual Testing
**Status**: Completed
**Time**: 5 min

Run manual tests:
```bash
# Test workflow creation
python -c "from src.graph.workflow import create_workflow; w = create_workflow(); print('✓ Workflow created')"

# Run full workflow
python main.py

# Check report file
ls -la reports/

# View report
cat reports/comparison-*.md

# Run unit tests
pytest tests/test_workflow.py -v
```

**Acceptance Criteria**:
- Workflow creates successfully
- main.py runs without errors
- Report file created in ./reports/
- All tests pass
- Placeholder messages visible in output

---

## Summary

**Total Tasks**: 9
**Estimated Time**: 53 minutes
**Dependencies**: Spec 001, 002 complete

## Checklist

- [x] 1. Create workflow module
- [x] 2. Implement parse_input_node()
- [x] 3. Implement generate_report_node()
- [x] 4. Create placeholder functions
- [x] 5. Implement create_workflow()
- [x] 6. Update module exports
- [x] 7. Update main.py
- [x] 8. Write tests
- [x] 9. Manual testing

---

**Status**: Ready to Start
