from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.api.routers.artifacts import router as artifacts_router
from app.api.routers.annotations import router as annotations_router
from app.api.routers.devices import router as devices_router
from app.api.routers.health import router as health_router
from app.api.routers.ingest import router as ingest_router
from app.api.routers.sessions import router as sessions_router
from app.api.routers.ws import router as ws_router
from app.core.lifecycle import run_shutdown_tasks, run_startup_checks
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import engine
from app.services.csv_writer import csv_writer_service
from app.services.video_recorder import video_recorder_service
from app.services.ws_runtime import ws_runtime


def _ensure_video_recordings_schema() -> None:
    inspector = inspect(engine)
    if "video_recordings" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("video_recordings")}
    with engine.begin() as conn:
        if "video_start_monotonic_ms" not in columns:
            conn.execute(text("ALTER TABLE video_recordings ADD COLUMN video_start_monotonic_ms INTEGER"))
        if "video_end_monotonic_ms" not in columns:
            conn.execute(text("ALTER TABLE video_recordings ADD COLUMN video_end_monotonic_ms INTEGER"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_video_recordings_schema()
    app.state.preflight_report = run_startup_checks()
    ws_runtime.start()
    yield
    await ws_runtime.stop()
    video_recorder_service.close_all()
    csv_writer_service.close_all()
    app.state.shutdown_report = run_shutdown_tasks()


app = FastAPI(
    title="IMU Collector Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(devices_router)
app.include_router(sessions_router)
app.include_router(ingest_router)
app.include_router(annotations_router)
app.include_router(artifacts_router)
app.include_router(ws_router)
