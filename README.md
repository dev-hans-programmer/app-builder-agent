# Dual-Stack Backend Builder Agent

AI-powered agent that generates backend applications in both Python (FastAPI) and Node.js (Express) from a single prompt, then provides intelligent comparison.

## Features

- 🐍 **Python/FastAPI** code generation
- 🟢 **Node.js/Express** code generation
- ⚡ **Parallel execution** of both builders
- 📊 **Intelligent comparison** and recommendation
- 🤖 **Powered by Claude** (Anthropic API)
- 🎯 **LangGraph orchestration**

## Setup

### Prerequisites

- Python 3.11 or higher
- An Anthropic API key ([Get one here](https://console.anthropic.com/))

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
   # Edit .env and add your ANTHROPIC_API_KEY
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
│   ├── prompts/         # Prompt templates
│   └── utils/           # Utilities
├── builds/              # Generated applications
├── reports/             # Comparison reports
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

Currently under active development following spec-driven development approach.

See `features/` directory for implementation progress:
- [x] 001-project-setup
- [ ] 002-state-management
- [ ] 003-workflow-graph
- [ ] 004-python-builder
- [ ] 005-nodejs-builder
- [ ] 006-comparison-agent
- [ ] 007-cli-interface

## License

MIT

## Contributing

This is a learning project. Feel free to explore and experiment!
