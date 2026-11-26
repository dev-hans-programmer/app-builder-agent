"""
Unit tests for Node.js builder agent.

Tests cover:
- create_nodejs_prompt(): Generating prompts for Claude
- Integration tests (optional mocked API tests)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.agents import nodejs_builder
from src.graph import create_initial_state, ensure_workspace_layout
from src.prompts.nodejs_builder_prompt import create_nodejs_prompt


class TestNodejsBuilderModelRequest:
    def test_uses_max_completion_tokens(self, monkeypatch, tmp_path):
        response = SimpleNamespace(
            id="chatcmpl-test",
            model="test-sol-model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```filename: index.js\nconsole.log('generated')\n```"
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
        monkeypatch.setattr(nodejs_builder, "OpenAI", lambda **kwargs: client)

        state = create_initial_state("Build API", "node-request-test")
        state["artifacts"] = ensure_workspace_layout(tmp_path)

        result = nodejs_builder.build(state)

        assert result["nodejs_output"]["status"] == "success"
        request = create.call_args.kwargs
        assert request["max_completion_tokens"] == 1234
        assert request["reasoning_effort"] == "low"
        assert "max_tokens" not in request
        assert "temperature" not in request


class TestCreateNodejsPrompt:
    """Test create_nodejs_prompt() function."""

    def test_includes_user_prompt(self):
        """Test that the generated prompt includes the user's request."""
        user_prompt = "Build a todo API with CRUD operations"
        project_name = "todo-api"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        assert user_prompt in prompt
        assert "todo API with CRUD operations" in prompt

    def test_includes_project_name(self):
        """Test that the generated prompt includes the project name."""
        user_prompt = "Build a simple API"
        project_name = "my-test-project"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        assert project_name in prompt
        assert "my-test-project" in prompt

    def test_includes_system_prompt(self):
        """Test that the generated prompt includes the system prompt."""
        user_prompt = "Build an API"
        project_name = "test"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        # Check for key elements from system prompt
        assert "Express" in prompt or "Express.js" in prompt
        assert "filename:" in prompt
        assert "package.json" in prompt
        assert "README.md" in prompt
        assert "Node.js" in prompt

    def test_mentions_express(self):
        """Test that the prompt specifically mentions Express.js."""
        user_prompt = "Build a REST API"
        project_name = "test-api"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        # Should mention Express since it's the target framework
        assert "Express" in prompt

    def test_mentions_es6_features(self):
        """Test that the prompt mentions modern JavaScript features."""
        user_prompt = "Build an API"
        project_name = "test"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        # Should mention ES6+ or async/await
        assert "ES6" in prompt or "async" in prompt or "await" in prompt

    def test_prompt_structure(self):
        """Test the overall structure of the generated prompt."""
        user_prompt = "Build a weather API"
        project_name = "weather-api"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        # Should have clear sections
        assert "Project Name:" in prompt
        assert "User Request:" in prompt
        assert "Generate a complete Express" in prompt

    def test_different_inputs(self):
        """Test with various user inputs."""
        test_cases = [
            ("Simple hello world API", "hello-api"),
            ("E-commerce backend with authentication", "ecommerce-backend"),
            ("Real-time chat API with WebSocket support", "chat-api")
        ]

        for user_prompt, project_name in test_cases:
            prompt = create_nodejs_prompt(user_prompt, project_name)

            assert user_prompt in prompt
            assert project_name in prompt
            assert len(prompt) > 0
            assert "Express" in prompt

    def test_includes_error_handling_requirements(self):
        """Test that prompt includes error handling requirements."""
        user_prompt = "Build a simple API"
        project_name = "test"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        # Should mention error handling
        assert "error" in prompt.lower() or "try" in prompt.lower()

    def test_includes_middleware_requirements(self):
        """Test that prompt mentions middleware."""
        user_prompt = "Build an API"
        project_name = "test"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        assert "middleware" in prompt.lower()

    def test_includes_jsdoc_requirements(self):
        """Test that prompt mentions JSDoc comments."""
        user_prompt = "Build an API"
        project_name = "test"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        assert "JSDoc" in prompt or "comment" in prompt.lower()

    def test_output_format_specified(self):
        """Test that the output format is clearly specified."""
        user_prompt = "Build an API"
        project_name = "test"

        prompt = create_nodejs_prompt(user_prompt, project_name)

        # Should specify the filename: format
        assert "```filename:" in prompt
        assert "[file contents" in prompt or "file contents" in prompt
