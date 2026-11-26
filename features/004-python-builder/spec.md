# Spec 004: Python Builder Agent

## Overview
Implement the Python/FastAPI builder agent that generates complete backend applications using Claude API.

## Scope

### In Scope
- Python builder agent node function
- Claude API integration for code generation
- Prompt template for Python/FastAPI
- File parsing from LLM response
- File writing to ./builds/python-{project}/
- Error handling and retry logic

### Out of Scope
- Code execution/validation (future enhancement)
- Syntax checking (rely on Claude)
- Database setup (future enhancement)
- Testing generation (future enhancement)

## Requirements

### 1. Prompt Template (src/prompts/python_builder_prompt.py)

```python
PYTHON_BUILDER_SYSTEM_PROMPT = """You are an expert Python backend developer specializing in FastAPI.

Your task is to generate a complete, production-ready FastAPI application based on the user's requirements.

IMPORTANT: Output each file using this exact format:
```filename: path/to/file.py
[file contents here]
```

Requirements:
1. Use FastAPI framework
2. Follow Python best practices (PEP 8)
3. Include type hints throughout
4. Use Pydantic models for request/response validation
5. Proper error handling with try-except blocks
6. Include a requirements.txt file
7. Include a README.md with setup instructions
8. Structure code properly (separate routes, models, config)
9. Add docstrings to functions

Start with requirements.txt, then main.py, then other files.
"""

def create_python_prompt(user_prompt: str, project_name: str) -> str:
    """Create the full prompt for Python builder"""
    return f"""{PYTHON_BUILDER_SYSTEM_PROMPT}

Project Name: {project_name}
User Request: {user_prompt}

Generate a complete FastAPI application that fulfills this request.
"""
```

### 2. Python Builder Agent (src/agents/python_builder.py)

```python
import os
import time
import re
from pathlib import Path
from anthropic import Anthropic
from src.graph.state import BuilderState
from src.prompts.python_builder_prompt import create_python_prompt

def build(state: BuilderState) -> BuilderState:
    """
    Build a Python/FastAPI application using Claude API.

    Steps:
    1. Create prompt from user request
    2. Call Claude API for code generation
    3. Parse response into file structure
    4. Write files to ./builds/python-{project_name}/
    5. Update state with results

    Args:
        state: Current workflow state

    Returns:
        Updated state with python_output field populated
    """
    start_time = time.time()

    try:
        # Get API key from environment
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        # Create client
        client = Anthropic(api_key=api_key)

        # Create prompt
        prompt = create_python_prompt(
            state["user_prompt"],
            state["project_name"]
        )

        print(f"[Python Builder] Generating code for: {state['project_name']}")

        # Call Claude API
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extract text from response
        content = response.content[0].text

        # Parse files from response
        files = parse_code_blocks(content)

        if not files:
            raise ValueError("No files generated from Claude response")

        # Write files to disk
        output_dir = f"./builds/python-{state['project_name']}"
        write_files(output_dir, files)

        # Update state with success
        state["python_output"] = {
            "status": "success",
            "output_dir": output_dir,
            "files_created": list(files.keys()),
            "framework": "FastAPI",
            "file_count": len(files)
        }
        state["python_build_time"] = time.time() - start_time

        print(f"[Python Builder] ✓ Created {len(files)} files in {output_dir}")

    except Exception as e:
        error_msg = f"Python builder failed: {str(e)}"
        state["errors"].append(error_msg)
        state["python_output"] = {
            "status": "failed",
            "error": str(e)
        }
        state["python_build_time"] = time.time() - start_time

        print(f"[Python Builder] ✗ Error: {error_msg}")

    return state


def parse_code_blocks(content: str) -> dict[str, str]:
    """
    Parse code blocks from Claude response.

    Expected format:
    ```filename: path/to/file.py
    [file contents]
    ```

    Args:
        content: Raw text from Claude API

    Returns:
        Dictionary mapping file paths to file contents
    """
    files = {}

    # Regex pattern to match code blocks with filename
    pattern = r'```filename:\s*(.+?)\n(.*?)```'

    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        filepath = match.group(1).strip()
        file_content = match.group(2).strip()
        files[filepath] = file_content

    return files


def write_files(output_dir: str, files: dict[str, str]) -> None:
    """
    Write generated files to disk.

    Args:
        output_dir: Base directory for the project
        files: Dictionary mapping file paths to contents
    """
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for filepath, content in files.items():
        full_path = Path(output_dir) / filepath

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
```

### 3. Integration with Workflow (src/graph/workflow.py)

Replace placeholder with actual builder:
```python
# Import the builder
from src.agents.python_builder import build as python_builder_build

# In create_workflow(), replace:
workflow.add_node("python_builder", python_builder_placeholder)
# With:
workflow.add_node("python_builder", python_builder_build)
```

### 4. Environment Setup

Ensure .env has:
```bash
ANTHROPIC_API_KEY=your_actual_key_here
CLAUDE_MODEL=claude-sonnet-4-5-20250929
```

## Success Criteria

- ✅ Claude API integration works
- ✅ Prompt template generates valid Python/FastAPI code
- ✅ Code blocks parsed correctly from response
- ✅ Files written to correct directory structure
- ✅ requirements.txt includes necessary dependencies
- ✅ README.md has setup instructions
- ✅ Error handling catches API failures
- ✅ Build time tracked in state
- ✅ Generated code is syntactically valid
- ✅ State updated correctly on success/failure

## Testing

### Manual Test
```bash
# Ensure API key is set
export ANTHROPIC_API_KEY="your_key"

# Run workflow
python main.py

# Check generated files
ls -la builds/python-*/
cat builds/python-*/main.py
cat builds/python-*/requirements.txt
```

### Unit Tests (tests/test_python_builder.py)
```python
def test_parse_code_blocks():
    """Test parsing code blocks from response"""
    content = '''
```filename: main.py
print("hello")
```

```filename: utils.py
def helper():
    pass
```
    '''
    files = parse_code_blocks(content)
    assert len(files) == 2
    assert "main.py" in files
    assert "utils.py" in files

def test_write_files(tmp_path):
    """Test file writing"""
    files = {
        "main.py": "print('hello')",
        "subdir/utils.py": "def func(): pass"
    }
    write_files(str(tmp_path), files)

    assert (tmp_path / "main.py").exists()
    assert (tmp_path / "subdir" / "utils.py").exists()

def test_build_with_mock(monkeypatch):
    """Test builder with mocked Claude API"""
    # Mock API call and test full flow
    pass
```

## Dependencies

- **Spec 001**: Project setup
- **Spec 002**: State management
- **Spec 003**: Workflow graph
- **API Key**: ANTHROPIC_API_KEY in .env

---

**Status**: Ready for Implementation
**Estimated Time**: 50-60 minutes
