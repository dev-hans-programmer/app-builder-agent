# Spec 005: Node.js Builder Agent

## Overview
Implement the Node.js/Express builder agent that generates complete backend applications using Claude API.

## Scope

### In Scope
- Node.js builder agent node function
- Claude API integration for code generation
- Prompt template for Node.js/Express
- File parsing from LLM response (reuse from 004)
- File writing to ./builds/nodejs-{project}/
- Error handling and retry logic

### Out of Scope
- Code execution/validation
- NPM package installation
- Database setup
- Testing generation

## Requirements

### 1. Prompt Template (src/prompts/nodejs_builder_prompt.py)

```python
NODEJS_BUILDER_SYSTEM_PROMPT = """You are an expert Node.js backend developer specializing in Express.

Your task is to generate a complete, production-ready Express application based on the user's requirements.

IMPORTANT: Output each file using this exact format:
```filename: path/to/file.js
[file contents here]
```

Requirements:
1. Use Express.js framework
2. Follow JavaScript/Node.js best practices
3. Use modern ES6+ syntax
4. Use async/await for asynchronous operations
5. Proper error handling with try-catch blocks
6. Include a package.json file with all dependencies
7. Include a README.md with setup instructions
8. Structure code properly (separate routes, controllers, middleware)
9. Add JSDoc comments to functions
10. Use proper HTTP status codes

Start with package.json, then server.js or index.js, then other files.
"""

def create_nodejs_prompt(user_prompt: str, project_name: str) -> str:
    """Create the full prompt for Node.js builder"""
    return f"""{NODEJS_BUILDER_SYSTEM_PROMPT}

Project Name: {project_name}
User Request: {user_prompt}

Generate a complete Express.js application that fulfills this request.
"""
```

### 2. Node.js Builder Agent (src/agents/nodejs_builder.py)

```python
import os
import time
from anthropic import Anthropic
from src.graph.state import BuilderState
from src.prompts.nodejs_builder_prompt import create_nodejs_prompt
from src.agents.python_builder import parse_code_blocks, write_files

def build(state: BuilderState) -> BuilderState:
    """
    Build a Node.js/Express application using Claude API.

    Steps:
    1. Create prompt from user request
    2. Call Claude API for code generation
    3. Parse response into file structure
    4. Write files to ./builds/nodejs-{project_name}/
    5. Update state with results

    Args:
        state: Current workflow state

    Returns:
        Updated state with nodejs_output field populated
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
        prompt = create_nodejs_prompt(
            state["user_prompt"],
            state["project_name"]
        )

        print(f"[Node.js Builder] Generating code for: {state['project_name']}")

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

        # Parse files from response (reuse parser from python_builder)
        files = parse_code_blocks(content)

        if not files:
            raise ValueError("No files generated from Claude response")

        # Write files to disk (reuse writer from python_builder)
        output_dir = f"./builds/nodejs-{state['project_name']}"
        write_files(output_dir, files)

        # Update state with success
        state["nodejs_output"] = {
            "status": "success",
            "output_dir": output_dir,
            "files_created": list(files.keys()),
            "framework": "Express",
            "file_count": len(files)
        }
        state["nodejs_build_time"] = time.time() - start_time

        print(f"[Node.js Builder] ✓ Created {len(files)} files in {output_dir}")

    except Exception as e:
        error_msg = f"Node.js builder failed: {str(e)}"
        state["errors"].append(error_msg)
        state["nodejs_output"] = {
            "status": "failed",
            "error": str(e)
        }
        state["nodejs_build_time"] = time.time() - start_time

        print(f"[Node.js Builder] ✗ Error: {error_msg}")

    return state
```

### 3. Integration with Workflow (src/graph/workflow.py)

Replace placeholder with actual builder:
```python
# Import the builder
from src.agents.nodejs_builder import build as nodejs_builder_build

# In create_workflow(), replace:
workflow.add_node("nodejs_builder", nodejs_builder_placeholder)
# With:
workflow.add_node("nodejs_builder", nodejs_builder_build)
```

## Success Criteria

- ✅ Claude API integration works
- ✅ Prompt template generates valid Node.js/Express code
- ✅ Code blocks parsed correctly (reusing python_builder parser)
- ✅ Files written to correct directory structure
- ✅ package.json includes necessary dependencies
- ✅ README.md has setup instructions
- ✅ Error handling catches API failures
- ✅ Build time tracked in state
- ✅ Generated code is syntactically valid
- ✅ State updated correctly on success/failure
- ✅ Parallel execution with Python builder works

## Testing

### Manual Test
```bash
# Run workflow (both builders should run)
python main.py

# Check generated files
ls -la builds/nodejs-*/
cat builds/nodejs-*/server.js
cat builds/nodejs-*/package.json

# Optional: Test Node.js app
cd builds/nodejs-test-project
npm install
# Check for syntax errors
node --check server.js
```

### Unit Tests (tests/test_nodejs_builder.py)
```python
def test_create_nodejs_prompt():
    """Test prompt generation"""
    prompt = create_nodejs_prompt("Build API", "test-app")
    assert "Build API" in prompt
    assert "test-app" in prompt
    assert "Express" in prompt

def test_build_with_mock(monkeypatch):
    """Test builder with mocked Claude API"""
    # Similar to Python builder test
    pass

def test_parallel_execution():
    """Verify both builders run in parallel"""
    # Time the workflow, should be close to slowest builder
    # not sum of both
    pass
```

## Dependencies

- **Spec 001**: Project setup
- **Spec 002**: State management
- **Spec 003**: Workflow graph
- **Spec 004**: Python builder (reuses parse/write functions)
- **API Key**: ANTHROPIC_API_KEY in .env

---

**Status**: Ready for Implementation
**Estimated Time**: 35-40 minutes (less than 004 due to code reuse)
