from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import get_settings
from app.core.lifecycle import run_startup_checks
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
    report = run_startup_checks()
    request.app.state.preflight_report = report
    return PreflightResponse(**report)


@router.get("/metrics/runtime")
async def get_runtime_metrics() -> dict:
    return await collect_runtime_metrics()


@router.post("/health/webcam-test-mode")
def run_webcam_test_mode(duration_seconds: int = 10) -> dict:
    return video_recorder_service.run_test_mode(duration_seconds=duration_seconds)


@router.get("/health/webcam-snapshot.jpg")
def get_webcam_snapshot() -> Response:
    try:
        jpeg_bytes = video_recorder_service.capture_webcam_snapshot_jpeg()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"webcam snapshot unavailable: {exc}") from exc

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
