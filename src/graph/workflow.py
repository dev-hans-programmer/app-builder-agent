"""
LangGraph workflow definition for the Python Project Builder Agent.

This module defines the workflow graph that orchestrates the multi-agent system,
including requirement analysis, clarification gating, architecture planning,
spec decomposition, execution planning, and Python project generation.
"""

from langgraph.graph import StateGraph, END
from src.graph.state import BuilderState
from src.graph.runtime import advance_job_phase
from src.observability import instrument_node


def _terminal_job_status(state: BuilderState) -> str:
    """Derive the terminal status without hiding explicit step failures."""
    current_status = state.get("job_status")
    if current_status in {"failed", "blocked"}:
        return current_status

    python_output = state.get("python_output") or {}
    if python_output.get("status") != "success":
        return "failed"

    quality = state.get("quality_results") or {}
    if quality and not quality.get("passed"):
        return "failed"
    traceability = state.get("traceability_result") or {}
    if traceability and not traceability.get("passed"):
        return "failed"

    return "completed"


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
    Generate the final delivery report and checkpoint.

    This is the final node before END. Creates the ./reports/ directory
    if it does not exist and saves the final delivery summary.

    Args:
        state: Current workflow state

    Returns:
        State unchanged (report saved to disk)

    Example:
        >>> state = create_initial_state("Test", "test")
        >>> state = generate_report_node(state)
    """
    from pathlib import Path
    from src.graph.runtime import ensure_workspace_layout
    from src.agents.final_reporter import persist_delivery_summary

    manifest = state.get("artifacts") or ensure_workspace_layout(
        ".",
        project_name=state.get("project_name"),
    )
    state["artifacts"] = manifest
    reports_dir = Path(manifest["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Finalize state before persisting delivery artifacts so checkpoints and
    # summaries reflect the terminal status rather than the preceding phase.
    state = advance_job_phase(
        state,
        "completed",
        status=_terminal_job_status(state),
    )
    summary_paths = persist_delivery_summary(state)
    state["artifacts"] = state.get("artifacts", {})
    state["artifacts"].update(summary_paths)

    # LangGraph applies an append reducer to `errors`. Returning the full state
    # here would append all existing errors a second time, so report only the
    # fields finalized by this node.
    return {
        "artifacts": state["artifacts"],
        "current_phase": state["current_phase"],
        "job_status": state["job_status"],
        "updated_at": state["updated_at"],
        **summary_paths,
    }


def _route_after_requirement_analysis(state: BuilderState) -> str:
    """Route to clarification or architecture based on open questions."""
    if not state.get("clarification_gate_enabled", True):
        return "acceptance_approval"
    requirements = state.get("requirements") or {}
    if requirements.get("open_questions"):
        return "clarification_gate"
    return "acceptance_approval"


def _route_after_clarification_gate(state: BuilderState) -> str:
    """Route onward once clarification questions have been asked."""
    if not state.get("clarification_gate_enabled", True):
        return "acceptance_approval"
    return "acceptance_approval"


def start_generation_node(state: BuilderState) -> dict:
    """Mark the transition from planning into task-level code generation."""
    return {"current_phase": "generation", "job_status": "running"}


def _route_after_builder(state: BuilderState) -> str:
    """Every selected build must pass through the shared quality gate."""
    return "quality_gate"


def _route_after_quality_gate(state: BuilderState) -> str:
    """Retry failed checks with a bounded repair loop."""
    quality = state.get("quality_results") or {}
    max_attempts = int(
        (state.get("execution_plan") or {})
        .get("retry_policy", {})
        .get("max_repair_attempts", 2)
    )
    if not quality.get("passed") and int(state.get("repair_attempt", 0)) < max_attempts:
        return "targeted_repair"
    return "traceability"


# Placeholder function retained for offline workflow tests.


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


def create_workflow(
    *, checkpointer=None, interrupt_after: list[str] | None = None
) -> StateGraph:
    """
    Create and compile the LangGraph workflow.

    Build the Python-only project generation workflow.

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
        python_builder
          ↓
        quality_gate (build/lint/type/test/smoke)
          ↓
        targeted_repair (bounded loop when checks fail)
          ↓
        traceability (requirements to verified patches)
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
    """
    # Import here to avoid circular imports
    from src.agents.python_builder import build as python_builder_build
    from src.agents.architect import analyze_architecture
    from src.agents.clarification_gate import clarify_requirements
    from src.agents.planner import plan_execution
    from src.agents.spec_generator import generate_specs
    from src.agents.requirement_analyst import (
        analyze_requirements,
        approve_acceptance_criteria,
    )
    from src.agents.quality_gate import run_quality_gate
    from src.agents.targeted_repair import repair_failed_checks
    from src.agents.traceability import check_requirement_traceability
    from src.policy import load_backend_policy

    # Create graph with BuilderState
    workflow = StateGraph(BuilderState)

    # Add instrumented nodes. Parent ids describe the logical workflow even
    # when a conditional edge skips a node.
    nodes = {
        "parse_input": (parse_input_node, "workflow"),
        "backend_policy": (load_backend_policy, "parse_input"),
        "requirement_analysis": (analyze_requirements, "backend_policy"),
        "clarification_gate": (clarify_requirements, "requirement_analysis"),
        "acceptance_approval": (approve_acceptance_criteria, "requirement_analysis"),
        "architecture_planning": (analyze_architecture, "acceptance_approval"),
        "spec_decomposition": (generate_specs, "architecture_planning"),
        "planning": (plan_execution, "spec_decomposition"),
        "generation_start": (start_generation_node, "planning"),
        "python_builder": (python_builder_build, "generation_start"),
        "quality_gate": (run_quality_gate, "python_builder"),
        "targeted_repair": (repair_failed_checks, "quality_gate"),
        "traceability": (check_requirement_traceability, "quality_gate-or-repair"),
        "generate_report": (generate_report_node, "traceability"),
    }
    for node_name, (node, parent_step_id) in nodes.items():
        workflow.add_node(
            node_name,
            instrument_node(node_name, node, parent_step_id=parent_step_id),
        )

    # Set entry point
    workflow.set_entry_point("parse_input")

    # Define edges for workflow flow
    # After parse_input, run requirement analysis first
    workflow.add_edge("parse_input", "backend_policy")
    workflow.add_edge("backend_policy", "requirement_analysis")

    # Clarification is handled inline when requirement analyzer finds gaps
    workflow.add_conditional_edges(
        "requirement_analysis",
        _route_after_requirement_analysis,
        {
            "clarification_gate": "clarification_gate",
            "acceptance_approval": "acceptance_approval",
        },
    )

    # Continue immediately after the inline clarification step
    workflow.add_conditional_edges(
        "clarification_gate",
        _route_after_clarification_gate,
        {
            "acceptance_approval": "acceptance_approval",
            END: END,
        },
    )

    workflow.add_edge("acceptance_approval", "architecture_planning")

    # Spec decomposition creates the hierarchical implementation plan
    workflow.add_edge("architecture_planning", "spec_decomposition")

    # Planning creates the execution schedule before code generation begins
    workflow.add_edge("spec_decomposition", "planning")
    workflow.add_edge("planning", "generation_start")

    workflow.add_edge("generation_start", "python_builder")
    workflow.add_conditional_edges(
        "python_builder",
        _route_after_builder,
        {"quality_gate": "quality_gate"},
    )

    workflow.add_conditional_edges(
        "quality_gate",
        _route_after_quality_gate,
        {
            "targeted_repair": "targeted_repair",
            "traceability": "traceability",
        },
    )
    workflow.add_edge("targeted_repair", "quality_gate")
    workflow.add_edge("traceability", "generate_report")

    # End after report generation
    workflow.add_edge("generate_report", END)

    # Compile and return
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
