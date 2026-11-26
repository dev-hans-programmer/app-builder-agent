# Dual-Stack Backend Builder Agent

AI-powered agent that generates backend applications in both Python (FastAPI) and Node.js (Express) from a single prompt, then provides intelligent comparison.

## Features

- 🐍 **Python/FastAPI** code generation
- 🟢 **Node.js/Express** code generation
- ⚡ **Parallel execution** of both builders
- 📊 **Intelligent comparison** and recommendation
- 🔎 **Run-scoped observability** with step attempts and artifact hashes
- 🧭 **Gated generation pipeline** with approved criteria, API/data contracts, task patches,
  quality checks, targeted repair, and requirement traceability
- 🏗️ **Policy-driven Python generation** from the versioned `backend-prompt.md`, with clean
  architecture tasks and a mandatory compliance report
- 🤖 **Powered by OpenAI**
- 🎯 **LangGraph orchestration**

## Setup

### Prerequisites

- Python 3.11 or higher
- An OpenAI API key

### Installation

1. **Clone the repository** (or navigate to project directory)

2. **Install dependencies:**
   ```bash
   pip install -e .
   ```

   Or with uv:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

4. **Run the agent:**
   ```bash
   python main.py
   ```

   Generate only one stack when a comparison is not needed:

   ```bash
   uv run python main.py --stack python
   uv run python main.py --stack nodejs
   ```

   `--stack both` remains the default and runs both builders in parallel.

## Usage

When you run the agent, you'll be prompted to:
1. Describe the backend application you want to build
2. Provide a project name

The agent will then generate the selected implementation. When `--stack both`
is selected, it also compares the two implementations and provides a detailed
comparison report.

See [Generation Pipeline](docs/generation-pipeline.md) for the artifacts, quality gates,
repair behavior, and completion rules used by every run.

Python runs always load `backend-prompt.md` before requirement analysis. To keep the policy in a
different location, set `BACKEND_POLICY_PATH`; the selected file is hashed and copied into the
project's `policy/` directory for reproducibility. Node.js-only runs do not load or apply it.

### Example

```bash
$ python main.py

What backend app do you want to build?
> Build a REST API for a todo app with authentication

Project name:
> todo-api

[Phase 1] Launching 2 builder agents in parallel...
[Phase 2] Launching comparison agent...

✓ Generated Apps:
  - ./builds/python-todo-api/
  - ./builds/nodejs-todo-api/

📊 Comparison Report: ./reports/comparison-2026-02-13T10:30:45.md
```

## Project Structure

```
app-builder-agent/
├── src/
│   ├── agents/          # Builder and comparison agents
│   ├── graph/           # LangGraph workflow
│   ├── observability/   # Run events, step artifacts, usage, and summaries
│   ├── policy/          # Python backend policy loading and task section selection
│   ├── prompts/         # Prompt templates
│   └── utils/           # Utilities
├── builds/              # Generated applications
├── reports/             # Comparison reports
├── projects/            # Generated projects and run traces
├── features/            # Feature specs (spec-driven development)
└── docs/                # Documentation (PRD, TRD)
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black src/ tests/
ruff check src/ tests/
```

## Project Status

Implemented: stack-selective generation, approved acceptance artifacts, architecture/API/data
contracts, Python production-policy enforcement, executable task generation, task-level patches,
quality gates, bounded repair, traceability, checkpoints, and run observability.

Planned next: queue-backed workers for durable long-running execution and external progress
tracking.

## License

MIT

## Contributing

This is a learning project. Feel free to explore and experiment!
