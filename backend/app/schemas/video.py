from pydantic import BaseModel


class VideoStatusResponse(BaseModel):
    status: str
    session_id: str
    video_id: str | None = None
    camera_id: str | None = None
    file_path: str | None = None
    backend: str | None = None
    elapsed_ms: int = 0
    frame_count: int = 0
    dropped_frame_estimate: int = 0


class VideoMetadataResponse(BaseModel):
    session_id: str
    camera_id: str
    fps: float
    width: int
    height: int
    codec: str
    video_start_server_time: str
    video_end_server_time: str
    duration_ms: int
    frame_count: int
    dropped_frame_estimate: int
    file_path: str
    status: str
    error: str | None = None
    backend: str | None = None
