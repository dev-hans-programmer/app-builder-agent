"""
Unit tests for Python builder agent.

Tests cover:
- parse_code_blocks(): Parsing Claude API responses
- write_files(): Writing files to disk
- create_python_prompt(): Generating prompts for Claude
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.agents import python_builder
from src.agents.python_builder import parse_code_blocks, write_files
from src.graph import create_initial_state, ensure_workspace_layout
from src.prompts.python_builder_prompt import create_python_prompt


class TestParseCodeBlocks:
    """Test parse_code_blocks() function."""

    def test_single_file(self):
        """Test parsing a single code block."""
        content = """
```filename: main.py
print("hello world")
```
        """
        files = parse_code_blocks(content)

        assert len(files) == 1
        assert "main.py" in files
        assert files["main.py"] == 'print("hello world")'

    def test_multiple_files(self):
        """Test parsing multiple code blocks."""
        content = """
```filename: main.py
print("hello")
```

```filename: utils.py
def helper():
    pass
```

```filename: config.py
DEBUG = True
```
        """
        files = parse_code_blocks(content)

        assert len(files) == 3
        assert "main.py" in files
        assert "utils.py" in files
        assert "config.py" in files
        assert 'print("hello")' in files["main.py"]
        assert "def helper():" in files["utils.py"]
        assert "DEBUG = True" in files["config.py"]

    def test_no_files(self):
        """Test when no code blocks are present."""
        content = "This is just text without any code blocks."
        files = parse_code_blocks(content)

        assert len(files) == 0
        assert files == {}

    def test_code_block_without_filename(self):
        """Test that code blocks without filename marker are ignored."""
        content = """
```python
# This block has no filename marker
print("ignored")
```

```filename: main.py
print("included")
```
        """
        files = parse_code_blocks(content)

        assert len(files) == 1
        assert "main.py" in files
        assert files["main.py"] == 'print("included")'

    def test_nested_paths(self):
        """Test parsing code blocks with nested directory paths."""
        content = """
```filename: api/routes/users.py
from fastapi import APIRouter
```

```filename: api/models/user.py
class User:
    pass
```
        """
        files = parse_code_blocks(content)

        assert len(files) == 2
        assert "api/routes/users.py" in files
        assert "api/models/user.py" in files

    def test_multiline_code(self):
        """Test parsing code blocks with multiple lines."""
        content = """
```filename: app.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
```
        """
        files = parse_code_blocks(content)

        assert len(files) == 1
        assert "app.py" in files
        code = files["app.py"]
        assert "from fastapi import FastAPI" in code
        assert "@app.get" in code
        assert "def read_root():" in code

    def test_empty_code_block(self):
        """Test that empty code blocks are ignored."""
        content = """
```filename: empty.py

```

```filename: valid.py
print("valid")
```
        """
        files = parse_code_blocks(content)

        # Empty blocks should be skipped
        assert "empty.py" not in files
        assert len(files) == 1
        assert "valid.py" in files


class TestWriteFiles:
    """Test write_files() function."""

    def test_flat_structure(self, tmp_path):
        """Test writing files in a flat directory structure."""
        files = {
            "main.py": "print('hello')",
            "config.py": "DEBUG = True",
            "requirements.txt": "fastapi\nuvicorn",
        }

        write_files(str(tmp_path), files)

        # Verify files exist
        assert (tmp_path / "main.py").exists()
        assert (tmp_path / "config.py").exists()
        assert (tmp_path / "requirements.txt").exists()

        # Verify content
        assert (tmp_path / "main.py").read_text() == "print('hello')"
        assert (tmp_path / "config.py").read_text() == "DEBUG = True"
        assert (tmp_path / "requirements.txt").read_text() == "fastapi\nuvicorn"

    def test_nested_directories(self, tmp_path):
        """Test writing files with nested directory structure."""
        files = {
            "main.py": "# main",
            "api/routes/users.py": "# users route",
            "api/routes/posts.py": "# posts route",
            "api/models/user.py": "# user model",
            "config/settings.py": "# settings",
        }

        write_files(str(tmp_path), files)

        # Verify all files exist
        assert (tmp_path / "main.py").exists()
        assert (tmp_path / "api" / "routes" / "users.py").exists()
        assert (tmp_path / "api" / "routes" / "posts.py").exists()
        assert (tmp_path / "api" / "models" / "user.py").exists()
        assert (tmp_path / "config" / "settings.py").exists()

        # Verify directories were created
        assert (tmp_path / "api").is_dir()
        assert (tmp_path / "api" / "routes").is_dir()
        assert (tmp_path / "api" / "models").is_dir()
        assert (tmp_path / "config").is_dir()

    def test_file_content_correctness(self, tmp_path):
        """Test that file contents are written correctly with UTF-8 encoding."""
        files = {
            "unicode.py": "# こんにちは (Hello in Japanese)",
            "emoji.py": "# 🚀 Rocket",
            "multiline.py": "line1\nline2\nline3",
        }

        write_files(str(tmp_path), files)

        # Verify UTF-8 encoding works
        assert (tmp_path / "unicode.py").read_text(
            encoding="utf-8"
        ) == "# こんにちは (Hello in Japanese)"
        assert (tmp_path / "emoji.py").read_text(encoding="utf-8") == "# 🚀 Rocket"
        assert (tmp_path / "multiline.py").read_text(
            encoding="utf-8"
        ) == "line1\nline2\nline3"

    def test_creates_output_directory(self, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        output_dir = tmp_path / "new_project"
        files = {"test.py": "# test"}

        # Directory doesn't exist yet
        assert not output_dir.exists()

        write_files(str(output_dir), files)

        # Directory should be created
        assert output_dir.exists()
        assert output_dir.is_dir()
        assert (output_dir / "test.py").exists()

    def test_overwrites_existing_files(self, tmp_path):
        """Test that existing files are overwritten."""
        filepath = tmp_path / "test.py"
        filepath.write_text("old content")

        files = {"test.py": "new content"}
        write_files(str(tmp_path), files)

        # File should be overwritten
        assert filepath.read_text() == "new content"


class TestPythonBuilderModelRequest:
    def test_uses_max_completion_tokens(self, monkeypatch, tmp_path):
        response = SimpleNamespace(
            id="chatcmpl-test",
            model="test-sol-model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```filename: main.py\nprint('generated')\n```"
                    )
                )
            ],
            usage=None,
        )
        create = MagicMock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-6.2-sol")
        monkeypatch.setenv("OPENAI_MAX_COMPLETION_TOKENS", "1234")
        monkeypatch.setattr(python_builder, "OpenAI", lambda **kwargs: client)

        state = create_initial_state("Build API", "python-request-test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)

        result = python_builder.build(state)

        assert result["python_output"]["status"] == "success"
        request = create.call_args.kwargs
        assert request["max_completion_tokens"] == 1234
        assert request["reasoning_effort"] == "low"
        assert "max_tokens" not in request

    def test_returns_only_new_error_for_append_reducer(self, monkeypatch, tmp_path):
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=MagicMock(side_effect=RuntimeError("model failed"))
                )
            )
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setattr(python_builder, "OpenAI", lambda **kwargs: client)

        state = create_initial_state("Build API", "python-error-test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)
        state["errors"] = ["existing error"]

        result = python_builder.build(state)

        assert result["python_output"]["status"] == "failed"
        assert result["errors"] == ["Python builder failed: model failed"]


class TestCreatePythonPrompt:
    """Test create_python_prompt() function."""

    def test_includes_user_prompt(self):
        """Test that the generated prompt includes the user's request."""
        user_prompt = "Build a todo API with CRUD operations"
        project_name = "todo-api"

        prompt = create_python_prompt(user_prompt, project_name)

        assert user_prompt in prompt
        assert "todo API with CRUD operations" in prompt

    def test_includes_project_name(self):
        """Test that the generated prompt includes the project name."""
        user_prompt = "Build a simple API"
        project_name = "my-test-project"

        prompt = create_python_prompt(user_prompt, project_name)

        assert project_name in prompt
        assert "my-test-project" in prompt

    def test_includes_system_prompt(self):
        """Test that the generated prompt includes the system prompt."""
        user_prompt = "Build an API"
        project_name = "test"

        prompt = create_python_prompt(user_prompt, project_name)

        # Check for key elements from system prompt
        assert "FastAPI" in prompt
        assert "Return JSON only" in prompt
        assert '"task_id"' in prompt
        assert '"policy_rule_ids"' in prompt
        assert "Python" in prompt or "python" in prompt

    def test_prompt_structure(self):
        """Test the overall structure of the generated prompt."""
        user_prompt = "Build a weather API"
        project_name = "weather-api"

        prompt = create_python_prompt(user_prompt, project_name)

        # Should have clear sections
        assert "Project Name:" in prompt
        assert "User Request:" in prompt
        assert "Generate a complete FastAPI application" in prompt

    def test_different_inputs(self):
        """Test with various user inputs."""
        test_cases = [
            ("Simple hello world API", "hello-api"),
            ("E-commerce backend with authentication", "ecommerce-backend"),
            ("Real-time chat API with WebSocket support", "chat-api"),
        ]

        for user_prompt, project_name in test_cases:
            prompt = create_python_prompt(user_prompt, project_name)

            assert user_prompt in prompt
            assert project_name in prompt
            assert len(prompt) > 0
            assert "FastAPI" in prompt
