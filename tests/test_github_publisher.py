from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx

from src.control_plane.infrastructure.github import GitHubPublisher

RUN_ID = UUID("11111111-2222-3333-4444-555555555555")
MARKER = f"[app-builder-run:{RUN_ID}]"


def _publisher(transport: httpx.MockTransport) -> GitHubPublisher:
    return GitHubPublisher(
        owner="hasanali",
        token="never-log-this-token",
        visibility="private",
        author_name="Hasan Ali",
        author_email="hasan@example.com",
        api_url="https://api.github.test",
        transport=transport,
    )


def test_publishes_generated_files_as_one_github_commit(tmp_path: Path) -> None:
    source = tmp_path / "python"
    (source / "app").mkdir(parents=True)
    (source / "app" / "main.py").write_text("print('todo')\n", encoding="utf-8")
    (source / "README.md").write_text("# Todo\n", encoding="utf-8")
    (source / ".env").write_text("SECRET=never-push\n", encoding="utf-8")
    (source / ".env.example").write_text("SECRET=\n", encoding="utf-8")
    blob_contents: list[bytes] = []
    created_repository: dict = {}
    created_tree: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/user":
            return httpx.Response(200, json={"login": "hasanali"})
        if request.method == "GET" and path == "/repos/hasanali/todo":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and path == "/user/repos":
            created_repository.update(json.loads(request.content))
            return httpx.Response(
                201,
                json={
                    "name": "todo",
                    "html_url": "https://github.test/hasanali/todo",
                    "default_branch": "main",
                    "owner": {"login": "hasanali"},
                },
            )
        if path == "/repos/hasanali/todo/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "initial-sha"}})
        if path == "/repos/hasanali/todo/git/commits/initial-sha":
            return httpx.Response(
                200, json={"message": "Initial commit", "tree": {"sha": "base-tree"}}
            )
        if path == "/repos/hasanali/todo/git/blobs":
            body = json.loads(request.content)
            import base64

            blob_contents.append(base64.b64decode(body["content"]))
            return httpx.Response(201, json={"sha": f"blob-{len(blob_contents)}"})
        if path == "/repos/hasanali/todo/git/trees":
            created_tree.update(json.loads(request.content))
            return httpx.Response(201, json={"sha": "generated-tree"})
        if path == "/repos/hasanali/todo/git/commits":
            body = json.loads(request.content)
            assert MARKER in body["message"]
            assert body["parents"] == ["initial-sha"]
            return httpx.Response(201, json={"sha": "generated-commit"})
        if path == "/repos/hasanali/todo/git/refs/heads/main":
            body = json.loads(request.content)
            assert body == {"sha": "generated-commit", "force": False}
            return httpx.Response(200, json={})
        raise AssertionError(f"Unexpected GitHub request: {request.method} {path}")

    async def publish():
        async with _publisher(httpx.MockTransport(handler)) as publisher:
            await publisher.verify_owner()
            name = await publisher.available_repository_name("todo")
            return await publisher.publish(
                source_root=source,
                repository_name=name,
                project_name="Todo",
                run_id=RUN_ID,
            )

    result = asyncio.run(publish())

    assert created_repository["private"] is True
    assert created_repository["auto_init"] is True
    assert MARKER in created_repository["description"]
    assert result.name == "todo"
    assert result.commit_sha == "generated-commit"
    assert result.file_count == 3
    assert b"SECRET=never-push" not in blob_contents
    assert b"SECRET=\n" in blob_contents
    assert {item["path"] for item in created_tree["tree"]} == {
        ".env.example",
        "README.md",
        "app/main.py",
    }


def test_existing_project_name_gets_random_suffix(monkeypatch) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/repos/hasanali/todo":
            return httpx.Response(200, json={"name": "todo"})
        if request.url.path == "/repos/hasanali/todo-abc123":
            return httpx.Response(404, json={"message": "Not Found"})
        raise AssertionError(f"Unexpected request: {request.url.path}")

    monkeypatch.setattr("secrets.token_hex", lambda _: "abc123")

    async def choose_name() -> str:
        async with _publisher(httpx.MockTransport(handler)) as publisher:
            return await publisher.available_repository_name("Todo")

    assert asyncio.run(choose_name()) == "todo-abc123"
    assert requested_paths == [
        "/repos/hasanali/todo",
        "/repos/hasanali/todo-abc123",
    ]


def test_redelivery_reuses_commit_created_by_same_run(tmp_path: Path) -> None:
    source = tmp_path / "python"
    source.mkdir()
    (source / "main.py").write_text("pass\n", encoding="utf-8")
    writes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method != "GET":
            writes.append(path)
        if path == "/repos/hasanali/todo":
            return httpx.Response(
                200,
                json={
                    "name": "todo",
                    "description": f"Generated Todo backend {MARKER}",
                    "html_url": "https://github.test/hasanali/todo",
                    "default_branch": "main",
                },
            )
        if path == "/repos/hasanali/todo/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "existing-commit"}})
        if path == "/repos/hasanali/todo/git/commits/existing-commit":
            return httpx.Response(
                200,
                json={
                    "message": f"Generated backend\n\n{MARKER}",
                    "tree": {"sha": "t"},
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {path}")

    async def publish():
        async with _publisher(httpx.MockTransport(handler)) as publisher:
            return await publisher.publish(
                source_root=source,
                repository_name="todo",
                project_name="Todo",
                run_id=RUN_ID,
            )

    result = asyncio.run(publish())
    assert result.commit_sha == "existing-commit"
    assert writes == []
