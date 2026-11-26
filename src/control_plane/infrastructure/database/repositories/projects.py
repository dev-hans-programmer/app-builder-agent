from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.infrastructure.database.models import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, project_id: UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_by_slug(self, slug: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.slug == slug))

    async def list(self, *, offset: int, limit: int) -> tuple[list[Project], int]:
        statement = (
            select(Project)
            .where(Project.archived_at.is_(None))
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list((await self.session.scalars(statement)).all())
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Project)
                .where(Project.archived_at.is_(None))
            )
            or 0
        )
        return items, total

    def add(self, project: Project) -> None:
        self.session.add(project)
