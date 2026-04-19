from pydantic import BaseModel


class VideoStatusResponse(BaseModel):
    status: str
    session_id: str
    video_id: str | None = None
    camera_id: str | None = None
    file_path: str | None = None
    elapsed_ms: int = 0
    frame_count: int = 0
    dropped_frame_estimate: int = 0
