"""
LangGraph workflow definition for the Dual-Stack Backend Builder Agent.

This module defines the workflow graph that orchestrates the multi-agent system,
including requirement analysis, clarification gating, architecture planning,
spec decomposition, execution planning, and parallel build execution.
"""

from langgraph.graph import StateGraph, END
from src.graph.state import BuilderState
from src.graph.runtime import advance_job_phase


def parse_input_node(state: BuilderState) -> BuilderState:
    """
    Parse and validate user input.

    This is the entry point of the workflow. Validates that user_prompt
    and project_name are present and properly formatted.

    Args:
        state: Current workflow state

    Returns:
        Updated state with any validation errors added to state["errors"]

    Example:
        >>> state = create_initial_state("Build API", "test-project")
        >>> state = parse_input_node(state)
        >>> len(state["errors"])
        0
    """
    # Validate user_prompt exists and is not empty
    if not state.get("user_prompt"):
        state["errors"].append("User prompt is required")

    # Validate project_name exists and is not empty
    if not state.get("project_name"):
        state["errors"].append("Project name is required")

    return state


def generate_report_node(state: BuilderState) -> BuilderState:
    """
    Generate final output and save comparison report to disk.

    This is the final node before END. Creates the ./reports/ directory
    if it doesn't exist and saves the comparison report with a timestamped filename.

    Args:
        state: Current workflow state

    Returns:
        State unchanged (report saved to disk)

    Example:
        >>> state = create_initial_state("Test", "test")
        >>> state["comparison_report"] = "# Report content"
        >>> state = generate_report_node(state)
        # Report saved to ./reports/comparison-<timestamp>.md
    """
    from pathlib import Path
    from src.graph.runtime import ensure_workspace_layout
    from src.agents.final_reporter import build_delivery_summary, persist_delivery_summary

    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    state["artifacts"] = manifest
    reports_dir = Path(manifest["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamped filename (sanitize colons and dots for filesystem)
    timestamp = state["timestamp"].replace(":", "-").replace(".", "-")
    filename = f"comparison-{timestamp}.md"
    filepath = reports_dir / filename

    delivery_summary = build_delivery_summary(state)
    report_content = state.get("comparison_report") or "# Comparison Report\n\nNo comparison report was generated."
    report_content = f"{report_content}\n\n---\n\n{delivery_summary}"

    # Write report to file if comparison report exists
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_content)

    summary_paths = persist_delivery_summary(state)
    state["artifacts"] = state.get("artifacts", {})
    state["artifacts"].update(summary_paths)

    # Finalize job metadata for the current workflow
    state = advance_job_phase(state, "completed", status="completed")
    state["job_status"] = "completed"
    state["current_phase"] = "completed"
    state.update(summary_paths)

    return state


def _route_after_requirement_analysis(state: BuilderState) -> str:
    """Route to clarification or architecture based on open questions."""
    if not state.get("clarification_gate_enabled", True):
        return "architecture_planning"
    requirements = state.get("requirements") or {}
    if requirements.get("open_questions"):
        return "clarification_gate"
    return "architecture_planning"


def _route_after_clarification_gate(state: BuilderState) -> str:
    """Route onward once clarification questions have been asked."""
    if not state.get("clarification_gate_enabled", True):
        return "architecture_planning"
    return "architecture_planning"


# Placeholder functions (will be replaced in Specs 004-006)


def python_builder_placeholder(state: BuilderState) -> dict:
    """
    Placeholder for Python builder (Spec 004).

    This placeholder will be replaced with the actual Python/FastAPI
    builder implementation in Spec 004.

    Args:
        state: Current workflow state

    Returns:
        Dict with only python_output field for state update
    """
    print("[placeholder] Python builder would run here")
    return {
        "python_output": {
            "status": "placeholder",
            "message": "Python builder not yet implemented",
        }
    }


def nodejs_builder_placeholder(state: BuilderState) -> dict:
    """
    Placeholder for Node.js builder (Spec 005).

    This placeholder will be replaced with the actual Node.js/Express
    builder implementation in Spec 005.

    Args:
        state: Current workflow state

    Returns:
        Dict with only nodejs_output field for state update
    """
    print("[placeholder] Node.js builder would run here")
    return {
        "nodejs_output": {
            "status": "placeholder",
            "message": "Node.js builder not yet implemented",
        }
    }


def comparison_placeholder(state: BuilderState) -> dict:
    """
    Placeholder for comparison agent (Spec 006).

    This placeholder will be replaced with the actual comparison agent
    implementation in Spec 006.

    Args:
        state: Current workflow state

    Returns:
        Dict with only comparison_report field for state update
    """
    print("[placeholder] Comparison agent would run here")
    return {
        "comparison_report": "# Comparison Report\n\nPlaceholder - not yet implemented"
    }


def create_workflow() -> StateGraph:
    """
    Create and compile the LangGraph workflow.

    Builds a workflow graph that orchestrates the dual-stack backend builder
    system with spec-driven planning and parallel execution of Python and
    Node.js builders.

    Workflow structure:
        START
          ↓
        parse_input (validates input)
          ↓
        requirement_analysis (normalizes requirements)
          ↓
        clarification_gate (optional pause/resume)
          ↓
        architecture_planning (design)
          ↓
        spec_decomposition (hierarchical specs)
          ↓
        planning (execution schedule)
          ↓
        execution_engine (controlled spec write)
          ↓
        verification (checks execution artifacts)
          ↓
        repair (patches failures if needed)
          ↓
          ├─→ python_builder (parallel)
          └─→ nodejs_builder (parallel)
          ↓
        comparison (waits for both)
          ↓
        generate_report (saves to disk)
          ↓
        END

    Returns:
        Compiled StateGraph ready for execution

    Example:
        >>> workflow = create_workflow()
        >>> state = create_initial_state("Build API", "test")
        >>> final_state = workflow.invoke(state)
        >>> assert final_state["python_output"] is not None
        >>> assert final_state["nodejs_output"] is not None
    """
    # Import here to avoid circular imports
    from src.agents.python_builder import build as python_builder_build
    from src.agents.nodejs_builder import build as nodejs_builder_build
    from src.agents.comparison import compare as comparison_agent
    from src.agents.architect import analyze_architecture
    from src.agents.clarification_gate import clarify_requirements
    from src.agents.executor import execute_spec
    from src.agents.planner import plan_execution
    from src.agents.verification import repair_execution, verify_execution
    from src.agents.spec_generator import generate_specs
    from src.agents.requirement_analyst import analyze_requirements

    # Create graph with BuilderState
    workflow = StateGraph(BuilderState)

    # Add nodes
    workflow.add_node("parse_input", parse_input_node)
    workflow.add_node("requirement_analysis", analyze_requirements)
    workflow.add_node("clarification_gate", clarify_requirements)
    workflow.add_node("architecture_planning", analyze_architecture)
    workflow.add_node("spec_decomposition", generate_specs)
    workflow.add_node("planning", plan_execution)
    workflow.add_node("execution_engine", execute_spec)
    workflow.add_node("verification", verify_execution)
    workflow.add_node("repair", repair_execution)
    workflow.add_node("python_builder", python_builder_build)
    workflow.add_node("nodejs_builder", nodejs_builder_build)
    workflow.add_node("comparison", comparison_agent)
    workflow.add_node("generate_report", generate_report_node)

    # Set entry point
    workflow.set_entry_point("parse_input")

    # Define edges for workflow flow
    # After parse_input, run requirement analysis first
    workflow.add_edge("parse_input", "requirement_analysis")

    # Clarification is handled inline when requirement analyzer finds gaps
    workflow.add_conditional_edges(
        "requirement_analysis",
        _route_after_requirement_analysis,
        {
            "clarification_gate": "clarification_gate",
            "architecture_planning": "architecture_planning",
        },
    )

    # Continue immediately after the inline clarification step
    workflow.add_conditional_edges(
        "clarification_gate",
        _route_after_clarification_gate,
        {
            "architecture_planning": "architecture_planning",
            END: END,
        },
    )

    # Spec decomposition creates the hierarchical implementation plan
    workflow.add_edge("architecture_planning", "spec_decomposition")

    # Planning creates the execution schedule before code generation begins
    workflow.add_edge("spec_decomposition", "planning")

    # Execution engine applies the current spec in a controlled way
    workflow.add_edge("planning", "execution_engine")

    # Verification and repair happen before the builders continue
    workflow.add_edge("execution_engine", "verification")
    workflow.add_edge("verification", "repair")

    # After repair, both builders run in parallel
    workflow.add_edge("repair", "python_builder")
    workflow.add_edge("repair", "nodejs_builder")

    # Both builders must complete before comparison
    workflow.add_edge("python_builder", "comparison")
    workflow.add_edge("nodejs_builder", "comparison")

    # After comparison, generate report
    workflow.add_edge("comparison", "generate_report")

    # End after report generation
    workflow.add_edge("generate_report", END)

    # Compile and return
    return workflow.compile()
