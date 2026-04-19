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
