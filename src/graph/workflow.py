"""
LangGraph workflow definition for the Dual-Stack Backend Builder Agent.

This module defines the workflow graph that orchestrates the multi-agent system,
including requirement analysis, clarification gating, architecture planning,
spec decomposition, execution planning, and parallel build execution.
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

    target_stack = state.get("target_stack", "both")
    selected_outputs = []
    if target_stack in {"python", "both"}:
        selected_outputs.append(state.get("python_output") or {})
    if target_stack in {"nodejs", "both"}:
        selected_outputs.append(state.get("nodejs_output") or {})

    if any(output.get("status") == "failed" for output in selected_outputs):
        return "failed"

    quality = state.get("quality_results") or {}
    if quality and not quality.get("passed"):
        return "failed"
    traceability = state.get("traceability_result") or {}
    if traceability and not traceability.get("passed"):
        return "failed"

    comparison = state.get("comparison_metadata") or {}
    builders_succeeded = selected_outputs and all(
        output.get("status") == "success" for output in selected_outputs
    )
    if (
        target_stack == "both"
        and builders_succeeded
        and comparison.get("status") == "failed"
    ):
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

    # Checkpoints created before stack selection was introduced remain
    # compatible and preserve the original dual-stack behavior.
    state.setdefault("target_stack", "both")
    if state["target_stack"] not in {"python", "nodejs", "both"}:
        state["errors"].append("Target stack must be one of: python, nodejs, both")

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
    from src.agents.final_reporter import (
        build_delivery_summary,
        persist_delivery_summary,
    )

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
    delivery_summary = build_delivery_summary(state)
    comparison_report = state.get("comparison_report")
    if comparison_report:
        timestamp = state["timestamp"].replace(":", "-").replace(".", "-")
        filepath = reports_dir / f"comparison-{timestamp}.md"
        report_content = f"{comparison_report}\n\n---\n\n{delivery_summary}"
        filepath.write_text(report_content, encoding="utf-8")
        state["artifacts"]["comparison_report_markdown"] = str(filepath)

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


def _route_to_builders(state: BuilderState) -> list[str]:
    """Select one or both code-generation branches for this job."""
    target_stack = state.get("target_stack", "both")
    if target_stack == "python":
        return ["python_builder"]
    if target_stack == "nodejs":
        return ["nodejs_builder"]
    return ["python_builder", "nodejs_builder"]


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


def _route_after_traceability(state: BuilderState) -> str:
    """Compare only complete dual-stack deliveries."""
    if (
        state.get("target_stack", "both") == "both"
        and (state.get("traceability_result") or {}).get("passed")
    ):
        return "comparison"
    return "generate_report"


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
        selected builder(s)
          ↓
        quality_gate (build/lint/type/test/smoke)
          ↓
        targeted_repair (bounded loop when checks fail)
          ↓
        traceability (requirements to verified patches)
          ↓
        comparison (dual-stack jobs only)
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
    from src.agents.planner import plan_execution
    from src.agents.spec_generator import generate_specs
    from src.agents.requirement_analyst import (
        analyze_requirements,
        approve_acceptance_criteria,
    )
    from src.agents.quality_gate import run_quality_gate
    from src.agents.targeted_repair import repair_failed_checks
    from src.agents.traceability import check_requirement_traceability

    # Create graph with BuilderState
    workflow = StateGraph(BuilderState)

    # Add instrumented nodes. Parent ids describe the logical workflow even
    # when a conditional edge skips a node or fans out both builders.
    nodes = {
        "parse_input": (parse_input_node, "workflow"),
        "requirement_analysis": (analyze_requirements, "parse_input"),
        "clarification_gate": (clarify_requirements, "requirement_analysis"),
        "acceptance_approval": (approve_acceptance_criteria, "requirement_analysis"),
        "architecture_planning": (analyze_architecture, "acceptance_approval"),
        "spec_decomposition": (generate_specs, "architecture_planning"),
        "planning": (plan_execution, "spec_decomposition"),
        "generation_start": (start_generation_node, "planning"),
        "python_builder": (python_builder_build, "generation_start"),
        "nodejs_builder": (nodejs_builder_build, "generation_start"),
        "quality_gate": (run_quality_gate, "python_builder+nodejs_builder"),
        "targeted_repair": (repair_failed_checks, "quality_gate"),
        "traceability": (check_requirement_traceability, "quality_gate-or-repair"),
        "comparison": (comparison_agent, "python_builder+nodejs_builder"),
        "generate_report": (generate_report_node, "comparison-or-builder"),
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
    workflow.add_edge("parse_input", "requirement_analysis")

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

    # Run only the requested builder branches. A list return value fans out both
    # builders in the same superstep for dual-stack jobs.
    workflow.add_conditional_edges(
        "generation_start",
        _route_to_builders,
        {
            "python_builder": "python_builder",
            "nodejs_builder": "nodejs_builder",
        },
    )

    # All selected generation branches join at the same post-generation gate.
    for builder_node in ("python_builder", "nodejs_builder"):
        workflow.add_conditional_edges(
            builder_node,
            _route_after_builder,
            {
                "quality_gate": "quality_gate",
            },
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
    workflow.add_conditional_edges(
        "traceability",
        _route_after_traceability,
        {
            "comparison": "comparison",
            "generate_report": "generate_report",
        },
    )

    # After comparison, generate report
    workflow.add_edge("comparison", "generate_report")

    # End after report generation
    workflow.add_edge("generate_report", END)

    # Compile and return
    return workflow.compile()
