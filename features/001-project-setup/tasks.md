# Tasks 001: Project Setup & Dependencies

## Task List

### 1. Create Directory Structure
**Status**: Completed
**Time**: 3 min

```bash
mkdir -p src/{agents,graph,prompts,utils}
mkdir -p tests
mkdir -p builds reports
touch src/__init__.py
touch src/agents/__init__.py
touch src/graph/__init__.py
touch src/prompts/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py
```

**Acceptance Criteria**:
- All directories exist
- All __init__.py files created
- builds/ and reports/ directories exist

---

### 2. Create pyproject.toml
**Status**: Completed
**Time**: 2 min

Create `pyproject.toml` with:
- Project metadata
- Python version requirement (>=3.11)
- Core dependencies: langgraph, anthropic, python-dotenv, rich
- Dev dependencies: pytest, black, ruff

**Acceptance Criteria**:
- File is valid TOML
- `pip install -e .` succeeds
- All dependencies install without errors

---

### 3. Create .env.example
**Status**: Completed
**Time**: 1 min

Create `.env.example` with:
- ANTHROPIC_API_KEY placeholder
- CLAUDE_MODEL with default value
- BUILDS_DIR and REPORTS_DIR with defaults

**Acceptance Criteria**:
- File exists
- Contains all required environment variables
- Includes helpful comments

---

### 4. Create .gitignore
**Status**: Completed
**Time**: 2 min

Create `.gitignore` to exclude:
- .env (but not .env.example)
- Virtual environments (.venv/, venv/)
- Python cache (__pycache__/, *.pyc)
- Generated outputs (builds/, reports/)
- IDE files (.vscode/, .idea/)

**Acceptance Criteria**:
- Sensitive files are excluded
- Generated files are excluded
- Example files are NOT excluded

---

### 5. Create README.md
**Status**: Completed
**Time**: 3 min

Create `README.md` with:
- Project title and description
- Setup instructions
- How to run
- Project status note

**Acceptance Criteria**:
- Clear setup instructions
- Commands are copy-pasteable
- Includes all prerequisites

---

### 6. Create Placeholder main.py
**Status**: Completed
**Time**: 2 min

Create `main.py` with:
- Shebang line
- Docstring
- main() function with placeholder print
- if __name__ == "__main__" guard

**Acceptance Criteria**:
- File is executable
- Runs without errors
- Prints welcome message

---

### 7. Validate Installation
**Status**: Completed
**Time**: 5 min

Run validation commands:
1. Check Python version (>=3.11)
2. Install dependencies: `pip install -e .`
3. Test imports for all core libraries
4. Run main.py

**Acceptance Criteria**:
- Python version is correct
- All dependencies install successfully
- All imports work
- main.py executes and prints message

---

## Summary

**Total Tasks**: 7
**Estimated Time**: 18 minutes
**Dependencies**: None (this is the first spec)

## Checklist

- [x] 1. Create directory structure
- [x] 2. Create pyproject.toml
- [x] 3. Create .env.example
- [x] 4. Update .gitignore
- [x] 5. Create README.md
- [x] 6. Create placeholder main.py
- [x] 7. Validate installation

---

**Status**: Ready to Start
