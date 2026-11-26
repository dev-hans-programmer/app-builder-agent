"""Least-privilege GitHub repository delivery through the Git database API."""

from __future__ import annotations

import asyncio
import base64
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx


class GitHubPublishingError(RuntimeError):
    """A sanitized GitHub delivery failure safe for logs and API responses."""


class RepositoryNameCollision(GitHubPublishingError):
    """The reserved repository name was claimed by another request."""


@dataclass(frozen=True)
class PublishedRepository:
    owner: str
    name: str
    url: str
    branch: str
    commit_sha: str
    commit_url: str
    file_count: int


@dataclass(frozen=True)
class SourceFile:
    path: str
    content: bytes


class GitHubPublisher:
    """Create one personal repository and atomically advance its generated-code commit."""

    _EXCLUDED_DIRECTORIES = frozenset(
        {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "node_modules",
            "venv",
        }
    )
    _SECRET_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})

    def __init__(
        self,
        *,
        owner: str,
        token: str,
        visibility: str,
        author_name: str | None,
        author_email: str | None,
        include_workflows: bool = False,
        api_url: str = "https://api.github.com",
        timeout_seconds: float = 30.0,
        blob_concurrency: int = 8,
        max_files: int = 2000,
        max_file_bytes: int = 25 * 1024 * 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.owner = owner.strip()
        self.token = token
        self.visibility = visibility
        self.author_name = author_name or "app-builder-agent"
        self.author_email = author_email or "app-builder-agent@users.noreply.github.com"
        self.include_workflows = include_workflows
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.blob_concurrency = blob_concurrency
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.transport = transport
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GitHubPublisher:
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "app-builder-agent",
            },
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def verify_owner(self) -> None:
        response = await self._request("GET", "/user", expected={200})
        authenticated_login = str(response.json().get("login") or "")
        if authenticated_login.casefold() != self.owner.casefold():
            raise GitHubPublishingError(
                "GITHUB_OWNER does not match the account authenticated by GITHUB_TOKEN"
            )

    async def available_repository_name(self, project_name: str) -> str:
        base = self._repository_slug(project_name)
        if await self._get_repository(base) is None:
            return base
        for _ in range(20):
            candidate = f"{base[:93].rstrip('-')}-{secrets.token_hex(3)}"
            if await self._get_repository(candidate) is None:
                return candidate
        raise GitHubPublishingError("Could not allocate an available repository name")

    async def publish(
        self,
        *,
        source_root: Path,
        repository_name: str,
        project_name: str,
        run_id: UUID,
    ) -> PublishedRepository:
        files = self.collect_files(source_root)
        marker = f"[app-builder-run:{run_id}]"
        repository = await self._get_repository(repository_name)
        if repository is None:
            repository = await self._create_repository(
                repository_name=repository_name,
                project_name=project_name,
                marker=marker,
            )
        elif marker not in str(repository.get("description") or ""):
            raise RepositoryNameCollision(
                f"Repository '{repository_name}' is not owned by this run"
            )

        branch = str(repository.get("default_branch") or "main")
        head_sha = await self._wait_for_head(repository_name, branch)
        head_commit = (
            await self._request(
                "GET",
                f"/repos/{self.owner}/{repository_name}/git/commits/{head_sha}",
                expected={200},
            )
        ).json()
        if marker in str(head_commit.get("message") or ""):
            return self._result(
                repository, repository_name, branch, head_sha, len(files)
            )

        semaphore = asyncio.Semaphore(self.blob_concurrency)

        async def create_blob(source: SourceFile) -> dict[str, Any]:
            async with semaphore:
                response = await self._request(
                    "POST",
                    f"/repos/{self.owner}/{repository_name}/git/blobs",
                    expected={201},
                    retry_forbidden=True,
                    json={
                        "content": base64.b64encode(source.content).decode("ascii"),
                        "encoding": "base64",
                    },
                )
                return {
                    "path": source.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": response.json()["sha"],
                }

        tree_entries = list(
            await asyncio.gather(*(create_blob(item) for item in files))
        )
        if not any(item.path == "README.md" for item in files):
            tree_entries.append(
                {"path": "README.md", "mode": "100644", "type": "blob", "sha": None}
            )
        tree_response = await self._request(
            "POST",
            f"/repos/{self.owner}/{repository_name}/git/trees",
            expected={201},
            retry_forbidden=True,
            json={"base_tree": head_commit["tree"]["sha"], "tree": tree_entries},
        )
        commit_response = await self._request(
            "POST",
            f"/repos/{self.owner}/{repository_name}/git/commits",
            expected={201},
            retry_forbidden=True,
            json={
                "message": f"Generated backend for {project_name}\n\n{marker}",
                "tree": tree_response.json()["sha"],
                "parents": [head_sha],
                "author": {
                    "name": self.author_name,
                    "email": self.author_email,
                },
            },
        )
        commit_sha = str(commit_response.json()["sha"])
        await self._request(
            "PATCH",
            f"/repos/{self.owner}/{repository_name}/git/refs/heads/{branch}",
            expected={200},
            retry_forbidden=True,
            json={"sha": commit_sha, "force": False},
        )
        return self._result(repository, repository_name, branch, commit_sha, len(files))

    def collect_files(self, source_root: Path) -> list[SourceFile]:
        root = source_root.resolve(strict=True)
        collected: list[SourceFile] = []
        for candidate in sorted(root.rglob("*")):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
            if self._excluded(relative):
                continue
            size = candidate.stat().st_size
            if size > self.max_file_bytes:
                raise GitHubPublishingError(
                    f"Generated file exceeds GitHub delivery limit: {relative.as_posix()}"
                )
            collected.append(
                SourceFile(path=relative.as_posix(), content=candidate.read_bytes())
            )
            if len(collected) > self.max_files:
                raise GitHubPublishingError(
                    f"Generated project exceeds the {self.max_files}-file delivery limit"
                )
        if not collected:
            raise GitHubPublishingError(
                "No generated files are available for GitHub delivery"
            )
        return collected

    async def _create_repository(
        self, *, repository_name: str, project_name: str, marker: str
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/user/repos",
            expected={201, 422},
            json={
                "name": repository_name,
                "description": f"Generated {project_name} backend {marker}",
                "private": self.visibility == "private",
                "auto_init": True,
            },
        )
        if response.status_code == 422:
            raise RepositoryNameCollision(
                f"Repository name '{repository_name}' became unavailable"
            )
        repository = response.json()
        actual_owner = str((repository.get("owner") or {}).get("login") or "")
        if actual_owner.casefold() != self.owner.casefold():
            raise GitHubPublishingError(
                "GitHub created the repository under an unexpected owner"
            )
        return repository

    async def _get_repository(self, repository_name: str) -> dict[str, Any] | None:
        response = await self._request(
            "GET",
            f"/repos/{self.owner}/{repository_name}",
            expected={200, 404},
        )
        return None if response.status_code == 404 else response.json()

    async def _wait_for_head(self, repository_name: str, branch: str) -> str:
        for attempt in range(10):
            response = await self._request(
                "GET",
                f"/repos/{self.owner}/{repository_name}/git/ref/heads/{branch}",
                expected={200, 404, 409},
            )
            if response.status_code == 200:
                return str(response.json()["object"]["sha"])
            await asyncio.sleep(0.25 * (attempt + 1))
        raise GitHubPublishingError("GitHub did not initialize the repository in time")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected: set[int],
        json: dict[str, Any] | None = None,
        retry_forbidden: bool = False,
    ) -> httpx.Response:
        if self.client is None:
            raise RuntimeError(
                "GitHubPublisher must be used as an async context manager"
            )
        response: httpx.Response | None = None
        attempts = 7 if retry_forbidden else 3
        for attempt in range(attempts):
            try:
                response = await self.client.request(method, path, json=json)
            except httpx.HTTPError as error:
                if attempt == attempts - 1:
                    raise GitHubPublishingError(
                        f"GitHub request failed: {type(error).__name__}"
                    ) from error
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            if response.status_code in expected:
                return response
            retryable_statuses = {429, 502, 503, 504}
            if retry_forbidden:
                retryable_statuses.add(403)
            if (
                response.status_code not in retryable_statuses
                or attempt == attempts - 1
            ):
                break
            await asyncio.sleep(0.25 * (2**attempt))
        assert response is not None
        try:
            message = str(response.json().get("message") or "GitHub API error")
        except (ValueError, AttributeError):
            message = "GitHub API error"
        permission_hint = ""
        if response.status_code == 403 and "/git/" in path:
            permission_hint = (
                " Configure the fine-grained GITHUB_TOKEN for this resource owner with"
                " Repository access: All repositories and Contents: Read and write."
            )
            if self.include_workflows:
                permission_hint += (
                    " CONTROL_GITHUB_PUBLISH_WORKFLOWS=true also requires Workflows:"
                    " Read and write."
                )
        raise GitHubPublishingError(
            f"GitHub API returned {response.status_code} for {method} {path}: "
            f"{message[:300]}.{permission_hint}"
        )

    def _result(
        self,
        repository: dict[str, Any],
        repository_name: str,
        branch: str,
        commit_sha: str,
        file_count: int,
    ) -> PublishedRepository:
        repository_url = str(
            repository.get("html_url")
            or f"https://github.com/{self.owner}/{repository_name}"
        )
        return PublishedRepository(
            owner=self.owner,
            name=repository_name,
            url=repository_url,
            branch=branch,
            commit_sha=commit_sha,
            commit_url=f"{repository_url}/commit/{commit_sha}",
            file_count=file_count,
        )

    def _excluded(self, relative: Path) -> bool:
        if any(part in self._EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
            return True
        if (
            not self.include_workflows
            and len(relative.parts) >= 2
            and relative.parts[:2] == (".github", "workflows")
        ):
            return True
        name = relative.name.lower()
        if name == ".env" or name.startswith(".env.") and name != ".env.example":
            return True
        return relative.suffix.lower() in self._SECRET_SUFFIXES or name.endswith(
            ("credentials.json", "secrets.json")
        )

    @staticmethod
    def _repository_slug(project_name: str) -> str:
        cleaned = "".join(
            character if character.isalnum() or character in "-_." else "-"
            for character in project_name.strip().lower()
        )
        cleaned = cleaned.strip("-.")[:100]
        return cleaned or "generated-backend"
