# Spec 001: Project Setup & Dependencies

## Overview
Set up the basic project structure, install dependencies, and configure the development environment for the Dual-Stack Backend Builder Agent.

## Scope

### In Scope
- Project directory structure
- Python dependency management (pyproject.toml)
- Environment variable configuration (.env)
- Git configuration (.gitignore)
- Basic README with setup instructions

### Out of Scope
- Agent implementation
- LangGraph workflow
- Claude API integration (will be tested in later specs)

## Requirements

### 1. Directory Structure
```
app-builder-agent/
├── main.py                  # Entry point (placeholder)
├── pyproject.toml          # Dependencies
├── .env.example            # Environment template
├── .env                    # Actual env (gitignored)
├── .gitignore              # Git ignore rules
├── README.md               # Project documentation
├── docs/
│   ├── PRD.md             # (already exists)
│   └── TRD.md             # (already exists)
├── features/              # (already exists)
├── src/
│   ├── __init__.py
│   ├── agents/
│   │   └── __init__.py
│   ├── graph/
│   │   └── __init__.py
│   ├── prompts/
│   │   └── __init__.py
│   └── utils/
│       └── __init__.py
├── builds/                # Generated apps (gitignored)
├── reports/               # Comparison reports (gitignored)
└── tests/
    └── __init__.py
```

### 2. Dependencies (pyproject.toml)
```toml
[project]
name = "app-builder-agent"
version = "0.1.0"
description = "Dual-stack backend builder agent using LangGraph"
requires-python = ">=3.11"
dependencies = [
    "langchain>=0.3.0",
    "langgraph>=0.2.0",
    "anthropic>=0.39.0",
    "python-dotenv>=1.0.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "black>=24.0.0",
    "ruff>=0.6.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
```

### 3. Environment Variables (.env.example)
```bash
# Claude API Key (required)
ANTHROPIC_API_KEY=your_api_key_here

# Model Configuration (optional)
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# Output Directories (optional)
BUILDS_DIR=./builds
REPORTS_DIR=./reports
```

### 4. Git Ignore (.gitignore)
```
# Environment
.env
.venv/
venv/
env/
*.pyc
__pycache__/

# Generated files
builds/
reports/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Python
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
```

### 5. Basic README.md
```markdown
# Dual-Stack Backend Builder Agent

AI-powered agent that generates backend applications in both Python (FastAPI) and Node.js (Express) from a single prompt, then provides intelligent comparison.

## Setup

1. Install dependencies:
   ```bash
   pip install -e .
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env and add your ANTHROPIC_API_KEY
   ```

3. Run the agent:
   ```bash
   python main.py
   ```

## Project Status

Currently under development. See `features/` directory for implementation progress.
```

### 6. Placeholder main.py
```python
#!/usr/bin/env python3
"""
Dual-Stack Backend Builder Agent
Entry point (to be implemented)
"""

def main():
    print("🤖 Dual-Stack Backend Builder Agent")
    print("Setup complete! Implementation coming soon...")

if __name__ == "__main__":
    main()
```

## Success Criteria

- ✅ All directories created
- ✅ pyproject.toml is valid and dependencies install successfully
- ✅ .env.example exists with all required variables
- ✅ .gitignore properly excludes sensitive and generated files
- ✅ README provides clear setup instructions
- ✅ main.py runs without errors
- ✅ All __init__.py files exist for proper package structure

## Testing

### Manual Verification
1. Clone/navigate to project directory
2. Run `pip install -e .`
3. Verify all dependencies install
4. Run `python main.py`
5. Verify placeholder message displays

### Validation Commands
```bash
# Check Python version
python --version  # Should be 3.11+

# Install dependencies
pip install -e .

# Verify imports work
python -c "import langgraph; import anthropic; import rich"

# Run main
python main.py
```

## Dependencies
None - this is the foundation spec.

---

**Status**: Ready for Implementation
**Estimated Time**: 15-20 minutes
