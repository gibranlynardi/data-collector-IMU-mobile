from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.schemas.health import HealthResponse, PreflightResponse

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
