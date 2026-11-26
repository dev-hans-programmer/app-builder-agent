# Technical Requirements Document: Dual-Stack Backend Builder Agent

> Historical baseline: this document describes the original one-shot prototype and is retained
> for design history. For implemented behavior, use [Current Architecture](current-architecture.md)
> and [Generation Pipeline](generation-pipeline.md).

## Overview
This document outlines the technical implementation details for the Dual-Stack Backend Builder Agent system. It translates the PRD requirements into concrete technical specifications.

---

## System Architecture

### High-Level Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    Main Application                          │
│  (main.py - Entry point & Orchestrator)                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangGraph Workflow                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. Parse User Input Node                             │  │
│  │  2. Launch Parallel Builder Nodes                     │  │
│  │     ├── Python Builder Node (FastAPI)                 │  │
│  │     └── Node.js Builder Node (Express)                │  │
│  │  3. Comparison Node                                    │  │
│  │  4. Report Generation Node                             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              External Services & Storage                     │
│  ├── Claude API (Sonnet/Opus)                               │
│  ├── File System (./builds/, ./reports/)                    │
│  └── State Management (LangGraph State)                     │
└─────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. **Orchestrator (main.py)**
- Entry point for the application
- Initializes LangGraph workflow
- Handles user input
- Displays progress and results

#### 2. **LangGraph State Management**
```python
class BuilderState(TypedDict):
    user_prompt: str
    project_name: str
    python_output: Optional[Dict[str, Any]]
    nodejs_output: Optional[Dict[str, Any]]
    comparison_report: Optional[str]
    errors: List[str]
    timestamp: str
```

#### 3. **Builder Agents**
Each builder agent is a LangGraph node that:
- Takes user prompt as input
- Uses Claude API to generate code
- Creates project structure
- Writes files to disk
- Returns metadata about generated app

#### 4. **Comparison Agent**
- Analyzes both implementations
- Generates comparison report
- Provides recommendations

---

## Technology Stack

### Core Technologies
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Language | Python | 3.11+ | Main runtime |
| Orchestration | LangGraph | Latest | Agent workflow |
| LLM | Claude API | Sonnet 4.5 | Code generation |
| SDK | Anthropic Python SDK | Latest | API interaction |
| Environment | python-dotenv | Latest | Config management |

### Dependencies (pyproject.toml)
```toml
[project]
name = "app-builder-agent"
version = "0.1.0"
description = "Dual-stack backend builder agent using LangGraph"
requires-python = ">=3.11"
dependencies = [
    "langchain>=0.1.0",
    "langgraph>=0.0.20",
    "anthropic>=0.18.0",
    "python-dotenv>=1.0.0",
    "pydantic>=2.0.0",
    "rich>=13.0.0",  # For beautiful CLI output
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
```

---

## File Structure

```
app-builder-agent/
├── main.py                      # Entry point
├── pyproject.toml              # Project dependencies
├── .env                        # Environment variables (API keys)
├── .gitignore
├── README.md
├── docs/
│   ├── PRD.md
│   └── TRD.md
├── src/
│   ├── __init__.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── python_builder.py   # Python FastAPI builder agent
│   │   ├── nodejs_builder.py   # Node.js Express builder agent
│   │   └── comparison.py       # Comparison agent
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py           # LangGraph state definition
│   │   └── workflow.py        # LangGraph workflow definition
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── python_builder_prompt.py
│   │   ├── nodejs_builder_prompt.py
│   │   └── comparison_prompt.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_writer.py     # File system operations
│   │   └── logger.py          # Logging utilities
│   └── templates/
│       ├── python/            # Template files for Python projects
│       └── nodejs/            # Template files for Node.js projects
├── projects/                  # Generated project workspaces (gitignored)
│   └── {project-name}/
│       ├── builds/
│       │   ├── python/
│       │   └── nodejs/
│       ├── architecture/
│       ├── checkpoints/
│       ├── execution/
│       ├── plans/
│       ├── reports/
│       ├── requirements/
│       ├── repairs/
│       ├── specs/
│       └── verification/
└── reports/                   # Comparison reports
    └── comparison-{timestamp}.md
```

---

## Detailed Component Specifications

### 1. State Definition (src/graph/state.py)

```python
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime

class BuilderState(TypedDict):
    """State shared across all nodes in the workflow"""

    # Input
    user_prompt: str
    project_name: str

    # Builder outputs
    python_output: Optional[Dict[str, Any]]
    nodejs_output: Optional[Dict[str, Any]]

    # Comparison output
    comparison_report: Optional[str]

    # Metadata
    timestamp: str
    errors: List[str]
    python_build_time: Optional[float]
    nodejs_build_time: Optional[float]
```

### 2. LangGraph Workflow (src/graph/workflow.py)

```python
from langgraph.graph import StateGraph, END
from src.graph.state import BuilderState
from src.agents import python_builder, nodejs_builder, comparison

def create_workflow() -> StateGraph:
    """Creates the LangGraph workflow"""

    workflow = StateGraph(BuilderState)

    # Add nodes
    workflow.add_node("parse_input", parse_input_node)
    workflow.add_node("python_builder", python_builder.build)
    workflow.add_node("nodejs_builder", nodejs_builder.build)
    workflow.add_node("comparison", comparison.compare)
    workflow.add_node("generate_report", generate_report_node)

    # Define edges
    workflow.set_entry_point("parse_input")

    # Parallel execution of builders
    workflow.add_edge("parse_input", "python_builder")
    workflow.add_edge("parse_input", "nodejs_builder")

    # Wait for both builders before comparison
    workflow.add_edge("python_builder", "comparison")
    workflow.add_edge("nodejs_builder", "comparison")

    workflow.add_edge("comparison", "generate_report")
    workflow.add_edge("generate_report", END)

    return workflow.compile()
```

### 3. Python Builder Agent (src/agents/python_builder.py)

```python
from anthropic import Anthropic
from src.graph.state import BuilderState
from src.prompts.python_builder_prompt import PYTHON_BUILDER_PROMPT
from src.utils.file_writer import write_project_files
import time

def build(state: BuilderState) -> BuilderState:
    """
    Builds a Python FastAPI application based on user prompt

    Steps:
    1. Construct prompt for Claude with user requirements
    2. Request code generation from Claude
    3. Parse response into file structure
    4. Write files to ./builds/python-{project-name}/
    5. Return metadata about generated app
    """

    start_time = time.time()

    try:
        client = Anthropic()

        # Construct the prompt
        prompt = PYTHON_BUILDER_PROMPT.format(
            user_prompt=state["user_prompt"],
            project_name=state["project_name"]
        )

        # Call Claude API
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response and extract file contents
        files = parse_code_response(response.content)

        # Write files to disk
        output_dir = f"./builds/python-{state['project_name']}"
        write_project_files(output_dir, files)

        # Update state
        state["python_output"] = {
            "status": "success",
            "output_dir": output_dir,
            "files_created": list(files.keys()),
            "framework": "FastAPI"
        }
        state["python_build_time"] = time.time() - start_time

    except Exception as e:
        state["errors"].append(f"Python builder error: {str(e)}")
        state["python_output"] = {"status": "failed", "error": str(e)}

    return state
```

### 4. Node.js Builder Agent (src/agents/nodejs_builder.py)

```python
# Similar structure to Python builder but with Node.js/Express specifics
def build(state: BuilderState) -> BuilderState:
    """
    Builds a Node.js Express application based on user prompt

    Steps:
    1. Construct prompt for Claude with user requirements
    2. Request code generation from Claude
    3. Parse response into file structure
    4. Write files to ./builds/nodejs-{project-name}/
    5. Return metadata about generated app
    """
    # Implementation similar to python_builder.py
    pass
```

### 5. Comparison Agent (src/agents/comparison.py)

```python
from anthropic import Anthropic
from src.graph.state import BuilderState
from src.prompts.comparison_prompt import COMPARISON_PROMPT

def compare(state: BuilderState) -> BuilderState:
    """
    Compares both implementations and generates a report

    Steps:
    1. Collect metadata from both builds
    2. Read key files from both implementations
    3. Send to Claude for analysis
    4. Generate comparison report
    """

    try:
        client = Anthropic()

        # Prepare comparison data
        comparison_data = {
            "python": state["python_output"],
            "nodejs": state["nodejs_output"],
            "user_prompt": state["user_prompt"]
        }

        # Construct prompt
        prompt = COMPARISON_PROMPT.format(**comparison_data)

        # Call Claude API
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        # Store report
        state["comparison_report"] = response.content[0].text

    except Exception as e:
        state["errors"].append(f"Comparison error: {str(e)}")

    return state
```

---

## Prompts

### Python Builder Prompt Template (src/prompts/python_builder_prompt.py)

```python
PYTHON_BUILDER_PROMPT = """
You are an expert Python backend developer specializing in FastAPI.

User Request: {user_prompt}
Project Name: {project_name}

Generate a complete, production-ready FastAPI application that fulfills the user's request.

Requirements:
1. Use FastAPI framework
2. Follow best practices and modern Python patterns
3. Include proper error handling
4. Add type hints
5. Create a requirements.txt file
6. Include a README.md with setup instructions
7. Use Pydantic models for data validation
8. Structure the code properly (routes, models, config)

Output Format:
For each file, use this format:
```filename: path/to/file.py
[file contents]
```

Start with the project structure, then provide all files.
"""
```

### Node.js Builder Prompt Template (src/prompts/nodejs_builder_prompt.py)

```python
NODEJS_BUILDER_PROMPT = """
You are an expert Node.js backend developer specializing in Express.

User Request: {user_prompt}
Project Name: {project_name}

Generate a complete, production-ready Express application that fulfills the user's request.

Requirements:
1. Use Express.js framework
2. Follow best practices and modern JavaScript/TypeScript patterns
3. Include proper error handling
4. Use async/await
5. Create a package.json file
6. Include a README.md with setup instructions
7. Use middleware appropriately
8. Structure the code properly (routes, controllers, models)

Output Format:
For each file, use this format:
```filename: path/to/file.js
[file contents]
```

Start with the project structure, then provide all files.
"""
```

### Comparison Prompt Template (src/prompts/comparison_prompt.py)

```python
COMPARISON_PROMPT = """
You are a senior software architect evaluating two backend implementations.

User's Original Request: {user_prompt}

Python Implementation (FastAPI):
- Build time: {python[build_time]}s
- Files created: {python[files_created]}
- Framework: FastAPI

Node.js Implementation (Express):
- Build time: {nodejs[build_time]}s
- Files created: {nodejs[files_created]}
- Framework: Express

Analyze both implementations and provide a comprehensive comparison covering:

1. **Code Quality & Maintainability**
   - Code organization
   - Readability
   - Best practices adherence

2. **Performance Characteristics**
   - Async/concurrency model
   - Expected throughput
   - Resource usage

3. **Developer Experience**
   - Ease of setup
   - Development workflow
   - Debugging capabilities

4. **Ecosystem & Libraries**
   - Available packages
   - Community support
   - Third-party integrations

5. **Scalability**
   - Horizontal scaling
   - Vertical scaling
   - Deployment options

6. **Use Case Fit**
   - Which implementation is better for this specific use case and why

Provide your analysis in markdown format with clear sections and a final recommendation.
"""
```

---

## File Writer Utility (src/utils/file_writer.py)

```python
import os
from pathlib import Path
from typing import Dict

def write_project_files(output_dir: str, files: Dict[str, str]) -> None:
    """
    Writes generated files to disk

    Args:
        output_dir: Base directory for the project
        files: Dictionary mapping file paths to file contents
    """

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Write each file
    for file_path, content in files.items():
        full_path = Path(output_dir) / file_path

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    print(f"✓ Created {len(files)} files in {output_dir}")
```

---

## Main Application (main.py)

```python
#!/usr/bin/env python3
"""
Main entry point for the Dual-Stack Backend Builder Agent
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.graph.workflow import create_workflow
from src.graph.state import BuilderState

# Load environment variables
load_dotenv()

console = Console()

def main():
    """Main application entry point"""

    # Display banner
    console.print("[bold cyan]🤖 Dual-Stack Backend Builder Agent[/bold cyan]")
    console.print("Builds your backend in Python (FastAPI) and Node.js (Express)\n")

    # Get user input
    user_prompt = console.input("[yellow]What backend app do you want to build?[/yellow] ")
    project_name = console.input("[yellow]Project name:[/yellow] ").strip().replace(" ", "-").lower()

    # Initialize state
    initial_state: BuilderState = {
        "user_prompt": user_prompt,
        "project_name": project_name,
        "python_output": None,
        "nodejs_output": None,
        "comparison_report": None,
        "timestamp": datetime.now().isoformat(),
        "errors": [],
        "python_build_time": None,
        "nodejs_build_time": None,
    }

    # Create workflow
    workflow = create_workflow()

    # Execute workflow
    console.print("\n[bold green][Phase 1][/bold green] Launching 2 builder agents in parallel...")
    console.print("  [+] python-agent launched (using FastAPI)")
    console.print("  [+] nodejs-agent launched (using Express)\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Building applications...", total=None)

        # Run the workflow
        final_state = workflow.invoke(initial_state)

        progress.update(task, completed=True)

    # Display results
    display_results(final_state)

def display_results(state: BuilderState):
    """Display final results to user"""

    console.print("\n[bold green]✓ Both implementations complete[/bold green]")
    console.print("[bold green]✓ Comparison report generated[/bold green]\n")

    # Display paths
    console.print("[bold]📁 Generated Apps:[/bold]")
    if state["python_output"] and state["python_output"]["status"] == "success":
        console.print(f"  - {state['python_output']['output_dir']}")
    if state["nodejs_output"] and state["nodejs_output"]["status"] == "success":
        console.print(f"  - {state['nodejs_output']['output_dir']}")

    # Save and display report
    report_path = f"./reports/comparison-{state['timestamp']}.md"
    os.makedirs("./reports", exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(state["comparison_report"])

    console.print(f"\n[bold]📊 Comparison Report:[/bold] {report_path}\n")

    # Display report preview
    console.print("[bold cyan]Report Preview:[/bold cyan]")
    console.print(state["comparison_report"][:500] + "...\n")

    # Display errors if any
    if state["errors"]:
        console.print("[bold red]⚠️  Errors encountered:[/bold red]")
        for error in state["errors"]:
            console.print(f"  - {error}")

if __name__ == "__main__":
    main()
```

---

## Environment Configuration

### .env file
```bash
# Claude API Key
ANTHROPIC_API_KEY=your_api_key_here

# Optional: Model configuration
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# Optional: Output directories
BUILDS_DIR=./builds
REPORTS_DIR=./reports
```

### .gitignore
```
# Environment
.env
.venv/
venv/
*.pyc
__pycache__/

# Generated files
builds/
reports/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
```

---

## Error Handling Strategy

### Error Types and Handling

1. **API Errors**
   - Rate limiting: Implement retry with exponential backoff
   - Authentication: Clear error message, check API key
   - Network errors: Retry up to 3 times

2. **File System Errors**
   - Permission issues: Check write permissions before starting
   - Disk space: Validate available space
   - Path errors: Sanitize and validate all paths

3. **Parsing Errors**
   - Invalid code format: Request regeneration from Claude
   - Incomplete response: Log and continue with other builder

4. **Builder Failures**
   - If one builder fails, continue with the other
   - Log error and include in final report
   - Comparison agent should handle missing data gracefully

---

## Performance Requirements

| Metric | Target | Notes |
|--------|--------|-------|
| Total execution time | < 2 minutes | For typical REST API project |
| API latency | < 30s per agent | Claude API response time |
| File write time | < 5s | For ~10-15 files |
| Memory usage | < 500MB | Peak memory during execution |
| Concurrent agents | 2 | Python and Node.js builders |

---

## Testing Strategy

### Unit Tests
```
tests/
├── test_agents/
│   ├── test_python_builder.py
│   ├── test_nodejs_builder.py
│   └── test_comparison.py
├── test_utils/
│   └── test_file_writer.py
└── test_workflow.py
```

### Test Cases

1. **Builder Tests**
   - Valid input produces valid output
   - Error handling for API failures
   - File structure validation
   - Dependency file validation (requirements.txt, package.json)

2. **Workflow Tests**
   - State transitions are correct
   - Parallel execution works
   - Error in one builder doesn't block the other

3. **Integration Tests**
   - End-to-end workflow execution
   - Generated apps are valid
   - Comparison report is generated

---

## Deployment & Execution

### Local Development Setup
```bash
# Clone repository
git clone <repo-url>
cd app-builder-agent

# Install dependencies
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Run the application
python main.py
```

### Running the Agent
```bash
# Interactive mode (default)
python main.py

# With CLI arguments (future enhancement)
python main.py --prompt "Build a REST API for task management" --name "task-api"
```

---

## Security Considerations

1. **API Key Management**
   - Store in .env file (never commit)
   - Validate presence on startup
   - Use environment variables in production

2. **File System Security**
   - Validate all file paths
   - Prevent directory traversal attacks
   - Sanitize project names

3. **Code Generation Safety**
   - Review generated code before execution
   - Sandbox execution environment (future)
   - Warn users about running generated code

---

## Monitoring & Logging

### Logging Strategy
```python
# Use Python's built-in logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app-builder-agent.log'),
        logging.StreamHandler()
    ]
)
```

### Metrics to Track
- Total execution time
- Per-agent execution time
- API call count and latency
- Success/failure rates
- File generation statistics

---

## Future Technical Enhancements

1. **Streaming Support**
   - Stream Claude API responses for real-time feedback
   - Display code as it's generated

2. **Caching**
   - Cache similar prompts to reduce API calls
   - Store common patterns and templates

3. **Validation**
   - Syntax validation for generated code
   - Automated testing of generated apps

4. **Enhanced Comparison**
   - Run actual performance benchmarks
   - Static code analysis metrics
   - Security vulnerability scanning

---

**Version**: 1.0
**Last Updated**: 2026-02-13
**Status**: Ready for Implementation
