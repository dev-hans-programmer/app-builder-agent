from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from src.control_plane.infrastructure.artifacts.port import StoredArtifact


class LocalArtifactStore:
    """Run-isolated filesystem store with traversal-safe reads."""

    _EXCLUDED_DIRECTORIES = frozenset(
        {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "__pycache__",
            "node_modules",
            "venv",
        }
    )

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def run_root(self, project_id: UUID, run_id: UUID) -> Path:
        path = self.root / "projects" / str(project_id) / "runs" / str(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def iter_files(self, root: Path) -> Iterator[Path]:
        """Yield durable artifacts without traversing runtime dependencies or links."""
        resolved_root = root.resolve(strict=True)
        self._assert_inside_root(resolved_root)
        for current, directories, filenames in os.walk(
            resolved_root, followlinks=False
        ):
            current_path = Path(current)
            directories[:] = [
                name
                for name in directories
                if name not in self._EXCLUDED_DIRECTORIES
                and not (current_path / name).is_symlink()
            ]
            for filename in filenames:
                path = current_path / filename
                if path.is_symlink() or not path.is_file():
                    continue
                yield path

    def inspect(self, path: Path) -> StoredArtifact:
        resolved = path.resolve(strict=True)
        self._assert_inside_root(resolved)
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return StoredArtifact(
            storage_key=str(resolved.relative_to(self.root)),
            filename=resolved.name,
            mime_type=mimetypes.guess_type(resolved.name)[0],
            sha256=digest.hexdigest(),
            size_bytes=resolved.stat().st_size,
        )

    def resolve(self, storage_key: str) -> Path:
        resolved = (self.root / storage_key).resolve(strict=True)
        self._assert_inside_root(resolved)
        if not resolved.is_file():
            raise FileNotFoundError(storage_key)
        return resolved

    def remove_tree(self, path: Path) -> str | None:
        """Remove one artifact subtree and return its root-relative storage key."""
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            return None
        self._assert_inside_root(resolved)
        if resolved == self.root or not resolved.is_dir():
            raise ValueError(
                "Artifact cleanup target must be a directory below the root"
            )
        storage_key = resolved.relative_to(self.root).as_posix()
        shutil.rmtree(resolved)
        return storage_key

    def _assert_inside_root(self, path: Path) -> None:
        if path != self.root and self.root not in path.parents:
            raise ValueError("Artifact path escapes the configured storage root")
