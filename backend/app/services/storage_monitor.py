from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass

from app.core.config import get_settings
from app.db.models import Session as SessionModel
from app.db.session import SessionLocal
from app.services.ws_runtime import ws_runtime

logger = logging.getLogger(__name__)


@dataclass
class StorageSessionReport:
    session_id: str
    free_bytes: int
    level: str


class StorageMonitorService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._task: asyncio.Task[None] | None = None
        self._last_level_by_session: dict[str, str] = {}
        self._safe_stop_in_progress: set[str] = set()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="storage-monitor-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def run_once(self) -> list[StorageSessionReport]:
        free_bytes = self._get_free_bytes()
        active_sessions = self._active_session_ids()
        reports: list[StorageSessionReport] = []

        for session_id in active_sessions:
            level = self._resolve_level(free_bytes)
            reports.append(StorageSessionReport(session_id=session_id, free_bytes=free_bytes, level=level))

            previous = self._last_level_by_session.get(session_id)
            self._last_level_by_session[session_id] = level

            if level == "ok":
                continue
            if previous == level:
                continue

            if level == "warning":
                ws_runtime.publish_warning_sync(
                    session_id,
                    device_id="backend",
                    warning=(
                        f"storage backend menipis: {free_bytes} bytes "
                        f"(threshold warning={self._settings.storage_runtime_warning_free_bytes})"
                    ),
                )
                ws_runtime.publish_session_event_sync(
                    session_id,
                    {
                        "type": "BACKEND_STORAGE_WARNING",
                        "session_id": session_id,
                        "free_bytes": free_bytes,
                        "threshold_warning_bytes": self._settings.storage_runtime_warning_free_bytes,
                    },
                )
                continue

            ws_runtime.publish_warning_sync(
                session_id,
                device_id="backend",
                warning=(
                    f"storage backend kritis: {free_bytes} bytes "
                    f"(threshold critical={self._settings.storage_runtime_critical_free_bytes})"
                ),
            )
            ws_runtime.publish_session_event_sync(
                session_id,
                {
                    "type": "BACKEND_STORAGE_CRITICAL",
                    "session_id": session_id,
                    "free_bytes": free_bytes,
                    "threshold_critical_bytes": self._settings.storage_runtime_critical_free_bytes,
                    "action": "stop_safe_recommended",
                },
            )
            if self._settings.storage_runtime_auto_safe_stop_on_critical:
                await self._safe_stop_session(session_id=session_id, free_bytes=free_bytes)

        stale_sessions = [session_id for session_id in self._last_level_by_session if session_id not in active_sessions]
        for session_id in stale_sessions:
            self._last_level_by_session.pop(session_id, None)

        return reports

    async def _loop(self) -> None:
        interval = max(1.0, float(self._settings.storage_runtime_check_interval_seconds))
        while True:
            await self.run_once()
            await asyncio.sleep(interval)

    def _get_free_bytes(self) -> int:
        try:
            return int(shutil.disk_usage(self._settings.data_root).free)
        except Exception:
            return 0

    def _active_session_ids(self) -> list[str]:
        with SessionLocal() as db:
            rows = (
                db.query(SessionModel.session_id)
                .filter(SessionModel.status.in_(["RUNNING", "SYNCING"]))
                .order_by(SessionModel.session_id.asc())
                .all()
            )
        return [session_id for (session_id,) in rows]

    def _resolve_level(self, free_bytes: int) -> str:
        if free_bytes <= self._settings.storage_runtime_critical_free_bytes:
            return "critical"
        if free_bytes <= self._settings.storage_runtime_warning_free_bytes:
            return "warning"
        return "ok"

    async def _safe_stop_session(self, *, session_id: str, free_bytes: int) -> None:
        if session_id in self._safe_stop_in_progress:
            return

        self._safe_stop_in_progress.add(session_id)
        try:
            from app.api.routers import sessions as sessions_router

            with SessionLocal() as db:
                session = db.get(SessionModel, session_id)
                if session is None or session.status not in {"RUNNING", "SYNCING"}:
                    return

                try:
                    await sessions_router.stop_session(session_id=session_id, db=db)
                except Exception as exc:
                    logger.exception("storage critical safe-stop failed for session %s", session_id)
                    ws_runtime.publish_session_event_sync(
                        session_id,
                        {
                            "type": "BACKEND_STORAGE_SAFE_STOP_FAILED",
                            "session_id": session_id,
                            "free_bytes": free_bytes,
                            "error": str(exc),
                        },
                    )
                    return

            ws_runtime.publish_session_event_sync(
                session_id,
                {
                    "type": "BACKEND_STORAGE_SAFE_STOP_TRIGGERED",
                    "session_id": session_id,
                    "free_bytes": free_bytes,
                },
            )
        finally:
            self._safe_stop_in_progress.discard(session_id)


storage_monitor_service = StorageMonitorService()
