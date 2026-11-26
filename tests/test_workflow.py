"""Tests for the Python-only LangGraph workflow."""

from pathlib import Path

from langgraph.graph import END, StateGraph

from src.graph import (
    BuilderState,
    create_initial_state,
    create_workflow,
    ensure_workspace_layout,
    generate_report_node,
    parse_input_node,
)


def test_parse_input_validates_required_fields() -> None:
    valid = parse_input_node(create_initial_state("Build API", "demo"))
    assert valid["errors"] == []

    invalid = BuilderState(
        user_prompt="",
        project_name="",
        python_output=None,
        timestamp="2026-01-01T00:00:00",
        errors=[],
        python_build_time=None,
    )
    result = parse_input_node(invalid)
    assert len(result["errors"]) == 2


def test_generate_report_writes_delivery_summary_only(tmp_path: Path) -> None:
    state = create_initial_state("Build API", "demo")
    state["artifacts"] = ensure_workspace_layout(tmp_path)
    state["python_output"] = {"status": "success"}
    state["quality_results"] = {"passed": True, "status": "passed"}
    state["traceability_result"] = {"passed": True, "status": "passed"}

    result = generate_report_node(state)

    summary = Path(result["delivery_summary_markdown"])
    assert summary.is_file()
    assert "# Delivery Summary" in summary.read_text(encoding="utf-8")
    assert not list(summary.parent.glob("comparison-*.md"))
    assert result["job_status"] == "completed"


def test_generate_report_preserves_python_failure(tmp_path: Path) -> None:
    state = create_initial_state("Build API", "demo")
    state["artifacts"] = ensure_workspace_layout(tmp_path)
    state["python_output"] = {"status": "failed", "error": "boom"}

    graph = StateGraph(BuilderState)
    graph.add_node("generate_report", generate_report_node)
    graph.set_entry_point("generate_report")
    graph.add_edge("generate_report", END)

    result = graph.compile().invoke(state)
    assert result["job_status"] == "failed"


def test_workflow_contains_one_builder_and_no_cross_stack_nodes() -> None:
    graph = create_workflow().get_graph()
    nodes = set(graph.nodes)

    assert "python_builder" in nodes
    assert "nodejs_builder" not in nodes
    assert "comparison" not in nodes
    assert "quality_gate" in nodes
    assert "traceability" in nodes


def test_offline_workflow_produces_only_python_output(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("REQUIREMENTS_MODEL_ENABLED", "false")

    final = create_workflow().invoke(create_initial_state("Build API", "demo"))

    assert final["python_output"]["status"] == "placeholder"
    assert "nodejs_output" not in final
    assert "comparison_report" not in final
