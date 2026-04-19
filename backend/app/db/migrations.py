from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection

from app.db.base import Base

MigrationFn = Callable[[Connection], None]


def _migration_add_video_monotonic_columns(conn: Connection) -> None:
    inspector = inspect(conn)
    if "video_recordings" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("video_recordings")}
    if "video_start_monotonic_ms" not in columns:
        conn.execute(text("ALTER TABLE video_recordings ADD COLUMN video_start_monotonic_ms INTEGER"))
    if "video_end_monotonic_ms" not in columns:
        conn.execute(text("ALTER TABLE video_recordings ADD COLUMN video_end_monotonic_ms INTEGER"))


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("20260419_0001_add_video_monotonic_columns", _migration_add_video_monotonic_columns),
]


def run_internal_migrations(engine: Engine) -> None:
    # Ensure latest model tables are present before patching legacy tables.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(128) PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        applied_versions = {
            row[0]
            for row in conn.execute(text("SELECT version FROM schema_migrations"))
        }

        for version, migration in MIGRATIONS:
            if version in applied_versions:
                continue
            migration(conn)
            conn.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": version},
            )
