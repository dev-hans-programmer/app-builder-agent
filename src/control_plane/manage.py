"""Administrative commands for non-Alembic infrastructure schemas."""

from __future__ import annotations

import argparse
import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text
from sqlalchemy.engine import make_url

from src.control_plane.config import get_settings
from src.control_plane.infrastructure.database.session import build_async_engine


_SCHEMA_METADATA_TABLES = {"alembic_version", "checkpoint_migrations"}


async def setup_checkpoints() -> None:
    async with AsyncPostgresSaver.from_conn_string(
        get_settings().checkpoint_database_url
    ) as checkpointer:
        await checkpointer.setup()


async def delete_all_database_data() -> list[str]:
    """Delete operational rows without dropping schemas or migration history."""
    engine = build_async_engine()
    try:
        async with engine.begin() as connection:
            schema = await connection.scalar(text("SELECT current_schema()"))
            if not schema:
                raise RuntimeError("The database connection has no current schema")

            result = await connection.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = :schema
                    ORDER BY tablename
                    """
                ),
                {"schema": schema},
            )
            tables = [
                str(row.tablename)
                for row in result
                if row.tablename not in _SCHEMA_METADATA_TABLES
            ]
            if not tables:
                return []

            quote = engine.dialect.identifier_preparer.quote_identifier
            qualified_tables = ", ".join(
                f"{quote(schema)}.{quote(table)}" for table in tables
            )
            await connection.execute(
                text(
                    f"TRUNCATE TABLE {qualified_tables} "
                    "RESTART IDENTITY CASCADE"
                )
            )
            return tables
    finally:
        await engine.dispose()


def confirm_database_deletion(database_url: str) -> None:
    url = make_url(database_url)
    database_name = url.database or ""
    host = url.host or "local socket"
    port = f":{url.port}" if url.port else ""
    print(
        "This permanently deletes all control-plane data from "
        f"'{database_name}' at {host}{port}."
    )
    print("Schemas and migration history will be preserved.")
    confirmation = input(f"Type the database name '{database_name}' to continue: ")
    if confirmation != database_name:
        raise SystemExit("Database cleanup cancelled; confirmation did not match.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("setup-checkpoints", "delete-all-data")
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the typed confirmation for delete-all-data",
    )
    arguments = parser.parse_args()
    if arguments.command == "setup-checkpoints":
        asyncio.run(setup_checkpoints())
        return

    settings = get_settings()
    if not arguments.yes:
        confirm_database_deletion(settings.database_url)
    deleted_tables = asyncio.run(delete_all_database_data())
    if deleted_tables:
        print(f"Deleted all data from {len(deleted_tables)} table(s):")
        print(", ".join(deleted_tables))
    else:
        print("No operational tables were found; nothing was deleted.")


if __name__ == "__main__":
    main()
