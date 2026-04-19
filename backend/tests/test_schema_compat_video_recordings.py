from sqlalchemy import create_engine, inspect, text

from app.db.migrations import run_internal_migrations


def test_ensure_video_recordings_schema_adds_monotonic_columns(tmp_path) -> None:
    db_file = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE video_recordings (
                    video_id VARCHAR(128) PRIMARY KEY,
                    session_id VARCHAR(64),
                    camera_id VARCHAR(64),
                    file_path VARCHAR(512),
                    status VARCHAR(32),
                    video_start_server_time DATETIME,
                    video_end_server_time DATETIME,
                    duration_ms INTEGER,
                    frame_count INTEGER,
                    dropped_frame_estimate INTEGER
                )
                """
            )
        )

    run_internal_migrations(engine)

    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("video_recordings")}
    assert "video_start_monotonic_ms" in columns
    assert "video_end_monotonic_ms" in columns
    assert "annotation_audits" in set(inspector.get_table_names())

    with engine.begin() as conn:
        versions = [row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))]
    assert "20260419_0001_add_video_monotonic_columns" in versions
