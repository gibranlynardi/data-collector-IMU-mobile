from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backend_host: str = "0.0.0.0"
    backend_rest_port: int = 8000
    backend_ws_port: int = 8001

    data_root: Path = Path("./data")
    database_url: str | None = None

    webcam_index: int = 0
    webcam_path: str | None = None
    webcam_min_fps: float = 15.0
    webcam_target_fps: float = 30.0
    webcam_target_width: int = 1280
    webcam_target_height: int = 720
    webcam_codec: str = "mp4v"
    webcam_min_free_bytes: int = 1_000_000_000
    ffmpeg_fallback_enabled: bool = True
    ffmpeg_executable: str = "ffmpeg"
    ffmpeg_camera_input: str | None = None
    ffmpeg_camera_format: str = "dshow"

    csv_flush_every_samples: int = 200
    csv_flush_every_seconds: float = 2.0
    csv_allow_recover_stale_lock: bool = True

    ws_device_timeout_seconds: int = 10
    ws_dashboard_queue_size: int = 128
    ws_max_batch_samples: int = 1000

    required_device_roles: str = Field(default="chest,waist,thigh")

    @property
    def required_roles(self) -> list[str]:
        return [r.strip() for r in self.required_device_roles.split(",") if r.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.data_root / "metadata.db"
        return f"sqlite:///{db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
