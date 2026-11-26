# Spec 003: LangGraph Workflow

## Overview
Create the LangGraph workflow that orchestrates the multi-agent system, defining nodes, edges, and execution flow.

## Scope

### In Scope
- Workflow graph definition with StateGraph
- Node functions (parse_input, generate_report)
- Edge definitions for node connections
- Parallel execution setup
- Workflow compilation

### Out of Scope
- Actual builder agent implementation (Specs 004-006)
- CLI interface (Spec 007)
- Error handling UI (handled in individual nodes)

## Requirements

### 1. Workflow Module (src/graph/workflow.py)

```python
from langgraph.graph import StateGraph, END
from src.graph.state import BuilderState
import time

def parse_input_node(state: BuilderState) -> BuilderState:
    """
    Parse and validate user input.

    This is the entry point of the workflow.
    Validates that user_prompt and project_name are present.
    """
    # Validation happens here
    if not state.get("user_prompt"):
        state["errors"].append("User prompt is required")

    if not state.get("project_name"):
        state["errors"].append("Project name is required")

    return state


def generate_report_node(state: BuilderState) -> BuilderState:
    """
    Generate final output and save comparison report to disk.

    This is the final node before END.
    Saves the comparison report to ./reports/
    """
    import os
    from pathlib import Path

    # Create reports directory
    reports_dir = Path("./reports")
    reports_dir.mkdir(exist_ok=True)

    # Generate filename
    timestamp = state["timestamp"].replace(":", "-").replace(".", "-")
    filename = f"comparison-{timestamp}.md"
    filepath = reports_dir / filename

    # Write report
    if state.get("comparison_report"):
        with open(filepath, "w") as f:
            f.write(state["comparison_report"])

    return state


def create_workflow() -> StateGraph:
    """
    Create and compile the LangGraph workflow.

    Workflow structure:
        parse_input
           ↓
        ┌──┴──┐
        │     │
     python nodejs
        │     │
        └──┬──┘
           ↓
      comparison
           ↓
    generate_report
           ↓
          END
    """
    # Create graph
    workflow = StateGraph(BuilderState)

    # Add nodes
    workflow.add_node("parse_input", parse_input_node)
    workflow.add_node("python_builder", python_builder_placeholder)
    workflow.add_node("nodejs_builder", nodejs_builder_placeholder)
    workflow.add_node("comparison", comparison_placeholder)
    workflow.add_node("generate_report", generate_report_node)

    # Set entry point
    workflow.set_entry_point("parse_input")

    # Define edges
    # After parse_input, both builders run in parallel
    workflow.add_edge("parse_input", "python_builder")
    workflow.add_edge("parse_input", "nodejs_builder")

    # Both builders must complete before comparison
    workflow.add_edge("python_builder", "comparison")
    workflow.add_edge("nodejs_builder", "comparison")

    # After comparison, generate report
    workflow.add_edge("comparison", "generate_report")

    # End after report generation
    workflow.add_edge("generate_report", END)

    # Compile and return
    return workflow.compile()


# Placeholder functions (will be replaced in Specs 004-006)
def python_builder_placeholder(state: BuilderState) -> BuilderState:
    """Placeholder for Python builder (Spec 004)"""
    print("[placeholder] Python builder would run here")
    state["python_output"] = {
        "status": "placeholder",
        "message": "Python builder not yet implemented"
    }
    return state


def nodejs_builder_placeholder(state: BuilderState) -> BuilderState:
    """Placeholder for Node.js builder (Spec 005)"""
    print("[placeholder] Node.js builder would run here")
    state["nodejs_output"] = {
        "status": "placeholder",
        "message": "Node.js builder not yet implemented"
    }
    return state


def comparison_placeholder(state: BuilderState) -> BuilderState:
    """Placeholder for comparison agent (Spec 006)"""
    print("[placeholder] Comparison agent would run here")
    state["comparison_report"] = "# Comparison Report\n\nPlaceholder - not yet implemented"
    return state
```

### 2. Export Workflow (src/graph/__init__.py)

Update to include workflow:
```python
from src.graph.state import (
    BuilderState,
    create_initial_state,
    sanitize_project_name,
    validate_state,
)
from src.graph.workflow import (
    create_workflow,
    parse_input_node,
    generate_report_node,
)

__all__ = [
    "BuilderState",
    "create_initial_state",
    "sanitize_project_name",
    "validate_state",
    "create_workflow",
    "parse_input_node",
    "generate_report_node",
]
```

### 3. Test the Workflow (main.py update)

Update main.py to test the workflow:
```python
#!/usr/bin/env python3
"""
Dual-Stack Backend Builder Agent
"""

from src.graph.state import create_initial_state
from src.graph.workflow import create_workflow

def main():
    print("🤖 Dual-Stack Backend Builder Agent")
    print("=" * 50)

    # Create initial state
    state = create_initial_state(
        user_prompt="Build a REST API for a todo app",
        project_name="Test Project"
    )

    # Create workflow
    workflow = create_workflow()

    # Run workflow
    print("\nRunning workflow...")
    final_state = workflow.invoke(state)

    # Display results
    print("\n✓ Workflow completed!")
    print(f"Project: {final_state['project_name']}")
    print(f"Python output: {final_state.get('python_output')}")
    print(f"Node.js output: {final_state.get('nodejs_output')}")
    print(f"Errors: {final_state.get('errors')}")

if __name__ == "__main__":
    main()
```

## Success Criteria

- ✅ StateGraph is created and compiled successfully
- ✅ All nodes are defined (even if placeholders)
- ✅ Edges create correct workflow flow
- ✅ Parallel execution works (python_builder and nodejs_builder run concurrently)
- ✅ parse_input_node validates state
- ✅ generate_report_node saves report to disk
- ✅ Workflow can be invoked with initial state
- ✅ Final state contains all expected fields
- ✅ No import errors

## Testing

### Manual Test
```bash
# Run the workflow
python main.py

# Expected output:
# - Workflow runs without errors
# - Placeholder messages printed
# - Report saved to ./reports/
```

### Integration Test (tests/test_workflow.py)
```python
def test_workflow_creation():
    """Test workflow can be created"""
    workflow = create_workflow()
    assert workflow is not None

def test_workflow_execution():
    """Test workflow runs end-to-end"""
    from src.graph.state import create_initial_state
    from src.graph.workflow import create_workflow

    state = create_initial_state("Test prompt", "test-project")
    workflow = create_workflow()

    final_state = workflow.invoke(state)

    assert final_state["user_prompt"] == "Test prompt"
    assert final_state["project_name"] == "test-project"
    assert "python_output" in final_state
    assert "nodejs_output" in final_state
    assert "comparison_report" in final_state

def test_parallel_execution():
    """Verify both builders run in parallel"""
    import time
    from src.graph.state import create_initial_state
    from src.graph.workflow import create_workflow

    start = time.time()

    state = create_initial_state("Test", "test")
    workflow = create_workflow()
    workflow.invoke(state)

    duration = time.time() - start

    # Should be fast since placeholders don't do much
    assert duration < 5.0
```

## Dependencies

- **Spec 001**: Project setup complete
- **Spec 002**: State management complete

---

**Status**: Ready for Implementation
**Estimated Time**: 35-40 minutes
