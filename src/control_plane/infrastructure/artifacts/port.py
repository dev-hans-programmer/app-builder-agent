from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class StoredArtifact:
    storage_key: str
    filename: str
    mime_type: str | None
    sha256: str
    size_bytes: int


class ArtifactStore(Protocol):
    def run_root(self, project_id: UUID, run_id: UUID) -> Path: ...
    def iter_files(self, root: Path) -> Iterator[Path]: ...
    def inspect(self, path: Path) -> StoredArtifact: ...
    def resolve(self, storage_key: str) -> Path: ...
    def remove_tree(self, path: Path) -> str | None: ...
