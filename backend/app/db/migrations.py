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


def _migration_add_sampling_quality_telemetry(conn: Connection) -> None:
    inspector = inspect(conn)

    if "devices" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("devices")}
        if "interval_p99_ms" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN interval_p99_ms FLOAT"))
        if "jitter_p99_ms" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN jitter_p99_ms FLOAT"))

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS device_sampling_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(64),
                device_id VARCHAR(64) NOT NULL,
                connected BOOLEAN DEFAULT 0,
                recording BOOLEAN DEFAULT 0,
                battery_percent FLOAT,
                storage_free_mb INTEGER,
                effective_hz FLOAT,
                interval_p99_ms FLOAT,
                jitter_p99_ms FLOAT,
                measured_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_device_sampling_telemetry_session_id ON device_sampling_telemetry(session_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_device_sampling_telemetry_device_id ON device_sampling_telemetry(device_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_device_sampling_telemetry_measured_at ON device_sampling_telemetry(measured_at)"))


def _migration_add_operator_action_audits(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS operator_action_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id VARCHAR(128) NOT NULL,
                operator_type VARCHAR(32) DEFAULT 'operator',
                action VARCHAR(128) NOT NULL,
                session_id VARCHAR(64),
                target_type VARCHAR(64),
                target_id VARCHAR(128),
                details_json TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_operator_action_audits_operator_id ON operator_action_audits(operator_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_operator_action_audits_action ON operator_action_audits(action)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_operator_action_audits_session_id ON operator_action_audits(session_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_operator_action_audits_created_at ON operator_action_audits(created_at)"))


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("20260419_0001_add_video_monotonic_columns", _migration_add_video_monotonic_columns),
    ("20260420_0002_add_sampling_quality_telemetry", _migration_add_sampling_quality_telemetry),
    ("20260420_0003_add_operator_action_audits", _migration_add_operator_action_audits),
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
