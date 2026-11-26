# Spec 006: Comparison Agent

## Overview
Implement the comparison agent that analyzes both Python and Node.js implementations and generates a comprehensive comparison report.

## Scope

### In Scope
- Comparison agent node function
- Prompt template for comparison analysis
- Claude API integration for analysis
- Markdown report generation
- Handling partial results (one builder failed)

### Out of Scope
- Performance benchmarking (runtime metrics)
- Code quality static analysis tools
- Automated testing comparison
- Cost estimation

## Requirements

### 1. Prompt Template (src/prompts/comparison_prompt.py)

```python
COMPARISON_SYSTEM_PROMPT = """You are a senior software architect with expertise in both Python and Node.js backend development.

Your task is to provide an objective, comprehensive comparison of two implementations of the same backend application.

Analyze the implementations across these dimensions:
1. **Code Quality & Maintainability**
2. **Performance Characteristics**
3. **Developer Experience**
4. **Ecosystem & Libraries**
5. **Scalability**
6. **Use Case Fit**

Format your response as a professional markdown report with clear sections, tables, and a final recommendation.
"""

def create_comparison_prompt(
    user_prompt: str,
    python_output: dict,
    nodejs_output: dict,
    python_files: dict[str, str] = None,
    nodejs_files: dict[str, str] = None
) -> str:
    """
    Create comparison prompt with implementation details.

    Args:
        user_prompt: Original user request
        python_output: Python builder output metadata
        nodejs_output: Node.js builder output metadata
        python_files: Optional dict of Python files (for deeper analysis)
        nodejs_files: Optional dict of Node.js files (for deeper analysis)

    Returns:
        Formatted prompt for Claude
    """

    # Build implementations summary
    python_status = python_output.get("status", "unknown")
    nodejs_status = nodejs_output.get("status", "unknown")

    python_info = ""
    if python_status == "success":
        python_info = f"""
**Python Implementation (FastAPI)**
- Status: Success
- Files created: {python_output.get('file_count', 0)}
- Files: {', '.join(python_output.get('files_created', []))}
- Build time: {python_output.get('build_time', 'N/A')}s
"""
    else:
        python_info = f"""
**Python Implementation (FastAPI)**
- Status: Failed
- Error: {python_output.get('error', 'Unknown error')}
"""

    nodejs_info = ""
    if nodejs_status == "success":
        nodejs_info = f"""
**Node.js Implementation (Express)**
- Status: Success
- Files created: {nodejs_output.get('file_count', 0)}
- Files: {', '.join(nodejs_output.get('files_created', []))}
- Build time: {nodejs_output.get('build_time', 'N/A')}s
"""
    else:
        nodejs_info = f"""
**Node.js Implementation (Express)**
- Status: Failed
- Error: {nodejs_output.get('error', 'Unknown error')}
"""

    prompt = f"""{COMPARISON_SYSTEM_PROMPT}

## User's Original Request
{user_prompt}

## Implementation Details

{python_info}

{nodejs_info}

## Your Task

Provide a comprehensive comparison report. Structure your response with these sections:

### Executive Summary
Brief overview of both implementations and key takeaway.

### Detailed Comparison

#### 1. Code Quality & Maintainability
- Code organization and structure
- Readability and clarity
- Best practices adherence
- Error handling approach

#### 2. Performance Characteristics
- Async/concurrency model
- Expected throughput
- Resource usage patterns
- Scalability potential

#### 3. Developer Experience
- Setup complexity
- Development workflow
- Debugging capabilities
- IDE/tooling support

#### 4. Ecosystem & Libraries
- Available packages
- Community support
- Third-party integrations
- Maturity of ecosystem

#### 5. Scalability Considerations
- Horizontal scaling
- Vertical scaling
- Deployment options
- Cloud platform support

#### 6. Use Case Fit
- Which implementation better suits this specific use case?
- Why?

### Comparison Table
Create a side-by-side comparison table with key metrics.

### Final Recommendation
Based on the specific use case ("{user_prompt}"), which stack would you recommend and why?

---

Generate your comparison report now.
"""

    return prompt
```

### 2. Comparison Agent (src/agents/comparison.py)

```python
import os
from anthropic import Anthropic
from src.graph.state import BuilderState
from src.prompts.comparison_prompt import create_comparison_prompt

def compare(state: BuilderState) -> BuilderState:
    """
    Compare Python and Node.js implementations using Claude API.

    Analyzes both implementations and generates a comprehensive
    markdown report with comparison and recommendation.

    Args:
        state: Current workflow state with builder outputs

    Returns:
        Updated state with comparison_report field populated
    """

    try:
        # Check if we have at least one successful build
        python_output = state.get("python_output", {})
        nodejs_output = state.get("nodejs_output", {})

        python_success = python_output.get("status") == "success"
        nodejs_success = nodejs_output.get("status") == "success"

        if not python_success and not nodejs_success:
            # Both failed - create error report
            state["comparison_report"] = create_error_report(
                "Both implementations failed to generate. Cannot perform comparison."
            )
            return state

        # Get API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        # Create client
        client = Anthropic(api_key=api_key)

        # Create prompt
        prompt = create_comparison_prompt(
            user_prompt=state["user_prompt"],
            python_output=python_output,
            nodejs_output=nodejs_output
        )

        print("[Comparison Agent] Analyzing implementations...")

        # Call Claude API with lower temperature for more analytical response
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=3000,
            temperature=0.3,  # Lower temperature for analysis
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extract comparison report
        report = response.content[0].text

        # Add metadata to report
        full_report = create_full_report(
            report=report,
            state=state,
            python_success=python_success,
            nodejs_success=nodejs_success
        )

        state["comparison_report"] = full_report

        print("[Comparison Agent] ✓ Comparison report generated")

    except Exception as e:
        error_msg = f"Comparison failed: {str(e)}"
        state["errors"].append(error_msg)
        state["comparison_report"] = create_error_report(error_msg)

        print(f"[Comparison Agent] ✗ Error: {error_msg}")

    return state


def create_error_report(error_message: str) -> str:
    """Create an error report when comparison cannot be performed"""
    return f"""# Comparison Report - Error

## Status
❌ Comparison could not be completed

## Error
{error_message}

## Details
The comparison agent requires at least one successful implementation to generate a meaningful comparison.

---
*Generated by Dual-Stack Backend Builder Agent*
"""


def create_full_report(
    report: str,
    state: BuilderState,
    python_success: bool,
    nodejs_success: bool
) -> str:
    """
    Add metadata and context to the comparison report.

    Args:
        report: Main comparison report from Claude
        state: Full workflow state
        python_success: Whether Python builder succeeded
        nodejs_success: Whether Node.js builder succeeded

    Returns:
        Full report with metadata
    """

    # Build status section
    status_section = f"""# Comparison Report

## Build Status

| Stack | Status | Build Time | Files Created |
|-------|--------|------------|---------------|
| Python (FastAPI) | {'✅ Success' if python_success else '❌ Failed'} | {state.get('python_build_time', 'N/A'):.2f}s | {state.get('python_output', {}).get('file_count', 0)} |
| Node.js (Express) | {'✅ Success' if nodejs_success else '❌ Failed'} | {state.get('nodejs_build_time', 'N/A'):.2f}s | {state.get('nodejs_output', {}).get('file_count', 0)} |

## Original Request
> {state['user_prompt']}

---

{report}

---

*Generated by Dual-Stack Backend Builder Agent on {state['timestamp']}*
"""

    return status_section
```

### 3. Integration with Workflow (src/graph/workflow.py)

Replace placeholder with actual comparison agent:
```python
from src.agents.comparison import compare

# In create_workflow(), replace:
workflow.add_node("comparison", comparison_placeholder)
# With:
workflow.add_node("comparison", compare)
```

## Success Criteria

- ✅ Comparison report generated successfully
- ✅ Report includes all required sections
- ✅ Handles case where one builder failed
- ✅ Handles case where both builders failed
- ✅ Report is well-formatted markdown
- ✅ Comparison is objective and balanced
- ✅ Recommendation is clear and justified
- ✅ Temperature set appropriately for analytical task
- ✅ Error handling is comprehensive

## Testing

### Manual Test
```bash
# Run full workflow
python main.py

# Check report
cat reports/comparison-*.md

# Verify report quality:
# - Has all sections
# - Markdown formatted
# - Tables render correctly
# - Recommendation is clear
```

### Test Cases
1. Both builders succeed → Full comparison
2. Only Python succeeds → Partial comparison
3. Only Node.js succeeds → Partial comparison
4. Both fail → Error report

## Dependencies

- **Spec 001**: Project setup
- **Spec 002**: State management
- **Spec 003**: Workflow graph
- **Spec 004**: Python builder
- **Spec 005**: Node.js builder

---

**Status**: Ready for Implementation
**Estimated Time**: 40-45 minutes
