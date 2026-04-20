from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.schemas.health import HealthResponse, PreflightResponse
from app.services.runtime_metrics import collect_runtime_metrics
from app.services.video_recorder import video_recorder_service

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        rest_port=settings.backend_rest_port,
        ws_port=settings.backend_ws_port,
    )


@router.get("/preflight")
def get_preflight(request: Request) -> PreflightResponse:
    report = getattr(request.app.state, "preflight_report", {})
    return PreflightResponse(**report)


@router.get("/metrics/runtime")
async def get_runtime_metrics() -> dict:
    return await collect_runtime_metrics()


@router.post("/health/webcam-test-mode")
def run_webcam_test_mode(duration_seconds: int = 10) -> dict:
    return video_recorder_service.run_test_mode(duration_seconds=duration_seconds)
