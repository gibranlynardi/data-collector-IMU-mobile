from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.artifacts import router as artifacts_router
from app.api.routers.annotations import router as annotations_router
from app.api.routers.devices import router as devices_router
from app.api.routers.health import router as health_router
from app.api.routers.sessions import router as sessions_router
from app.core.lifecycle import run_shutdown_tasks, run_startup_checks
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.preflight_report = run_startup_checks()
    yield
    app.state.shutdown_report = run_shutdown_tasks()


app = FastAPI(
    title="IMU Collector Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(devices_router)
app.include_router(sessions_router)
app.include_router(annotations_router)
app.include_router(artifacts_router)
