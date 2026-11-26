from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.application.commands import CreateProjectCommand
from src.control_plane.application.errors import ConflictError, NotFoundError
from src.control_plane.infrastructure.database.models import Project
from src.control_plane.infrastructure.database.repositories import ProjectRepository


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80]
    return slug or "project"


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.projects = ProjectRepository(session)

    async def create(self, command: CreateProjectCommand) -> Project:
        project = Project(
            name=command.name.strip(),
            slug=slugify(command.slug or command.name),
            description=command.description,
        )
        self.projects.add(project)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError(
                f"Project slug '{project.slug}' already exists"
            ) from error
        await self.session.refresh(project)
        return project

    async def require(self, project_id: UUID) -> Project:
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        return project

    async def update(self, project_id: UUID, changes: dict) -> Project:
        project = await self.require(project_id)
        for field, value in changes.items():
            if field == "name" and value is None:
                raise ConflictError("Project name cannot be null")
            setattr(project, field, value.strip() if isinstance(value, str) else value)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def archive(self, project_id: UUID) -> None:
        project = await self.require(project_id)
        project.archived_at = datetime.now(timezone.utc)
        await self.session.commit()
