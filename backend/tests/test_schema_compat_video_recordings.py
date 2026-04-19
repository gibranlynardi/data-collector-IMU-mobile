from sqlalchemy import create_engine, inspect, text

import app.main as main_app


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

    original_engine = main_app.engine
    main_app.engine = engine
    try:
        main_app._ensure_video_recordings_schema()
        columns = {c["name"] for c in inspect(engine).get_columns("video_recordings")}
        assert "video_start_monotonic_ms" in columns
        assert "video_end_monotonic_ms" in columns
    finally:
        main_app.engine = original_engine
