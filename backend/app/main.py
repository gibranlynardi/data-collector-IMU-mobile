from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.artifacts import router as artifacts_router
from app.api.routers.annotations import router as annotations_router
from app.api.routers.devices import router as devices_router
from app.api.routers.health import router as health_router
from app.api.routers.ingest import router as ingest_router
from app.api.routers.sessions import router as sessions_router
from app.api.routers.ws import router as ws_router
from app.core.config import get_settings
from app.core.lifecycle import run_shutdown_tasks, run_startup_checks
from app.db import models  # noqa: F401
from app.db.migrations import run_internal_migrations
from app.db.session import engine
from app.services.csv_writer import csv_writer_service
from app.services.storage_monitor import storage_monitor_service
from app.services.video_recorder import video_recorder_service
from app.services.ws_runtime import ws_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_internal_migrations(engine)
    app.state.preflight_report = run_startup_checks()
    ws_runtime.start()
    storage_monitor_service.start()
    yield
    await storage_monitor_service.stop()
    await ws_runtime.stop()
    video_recorder_service.close_all()
    csv_writer_service.close_all()
    app.state.shutdown_report = run_shutdown_tasks()


app = FastAPI(
    title="IMU Collector Backend",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(devices_router)
app.include_router(sessions_router)
app.include_router(ingest_router)
app.include_router(annotations_router)
app.include_router(artifacts_router)
app.include_router(ws_router)
