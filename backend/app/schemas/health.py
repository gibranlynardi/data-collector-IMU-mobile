from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    rest_port: int
    ws_port: int


class PreflightResponse(BaseModel):
    backend_healthy: bool
    storage_path_writable: bool
    storage_free_bytes: int
    webcam_connected: bool = False
    webcam_preview_ok: bool = False
    webcam_fps: float = 0.0
    webcam_fps_ok: bool = False
    webcam_storage_ok: bool = False
    webcam_available: bool
    webcam_detail: str
