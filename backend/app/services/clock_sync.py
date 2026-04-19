from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.ws_runtime import ws_runtime


@dataclass
class SessionTimeAuthority:
    server_start_time_unix_ns: int
    session_start_monotonic_ms: int


class ClockSyncService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._session_time_authority: dict[str, SessionTimeAuthority] = {}

    def mark_session_started(
        self,
        session_id: str,
        started_at: datetime,
        *,
        agreed_server_start_time_unix_ns: int | None = None,
        agreed_session_start_monotonic_ms: int | None = None,
    ) -> SessionTimeAuthority:
        started_at_utc = started_at.replace(tzinfo=UTC)
        authority = SessionTimeAuthority(
            server_start_time_unix_ns=(
                int(agreed_server_start_time_unix_ns)
                if agreed_server_start_time_unix_ns is not None
                else int(started_at_utc.timestamp() * 1_000_000_000)
            ),
            session_start_monotonic_ms=(
                int(agreed_session_start_monotonic_ms)
                if agreed_session_start_monotonic_ms is not None
                else int(time.monotonic() * 1000)
            ),
        )
        self._session_time_authority[session_id] = authority
        return authority

    def get_server_start_time_unix_ns(self, session_id: str) -> int | None:
        authority = self._session_time_authority.get(session_id)
        if authority is not None:
            return authority.server_start_time_unix_ns

        report = self.read_sync_report(session_id)
        value = report.get("server_start_time_unix_ns")
        return int(value) if value is not None else None

    def get_session_start_monotonic_ms(self, session_id: str) -> int | None:
        authority = self._session_time_authority.get(session_id)
        if authority is not None:
            return authority.session_start_monotonic_ms

        report = self.read_sync_report(session_id)
        value = report.get("session_start_monotonic_ms")
        return int(value) if value is not None else None

    async def run_preflight_sync(
        self,
        *,
        session_id: str,
        device_ids: list[str],
    ) -> dict[str, Any]:
        timeout_seconds = max(self._settings.clock_sync_probe_timeout_ms, 50) / 1000.0
        attempts = max(self._settings.clock_sync_attempts, 1)

        devices: list[dict[str, Any]] = []
        for device_id in sorted(set(device_ids)):
            offsets: list[float] = []
            latencies: list[float] = []

            for _ in range(attempts):
                probe = await ws_runtime.request_clock_sync_probe(session_id, device_id, timeout_seconds=timeout_seconds)
                if probe is None:
                    continue

                server_send_ns = int(probe["server_send_unix_ns"])
                server_recv_ns = int(probe["server_recv_unix_ns"])
                device_unix_ns = int(probe["device_unix_ns"])
                rtt_ns = max(0, server_recv_ns - server_send_ns)
                one_way_ns = rtt_ns / 2.0
                estimated_server_at_device_ns = server_send_ns + one_way_ns

                offset_ms = (device_unix_ns - estimated_server_at_device_ns) / 1_000_000.0
                latency_ms = rtt_ns / 1_000_000.0
                offsets.append(offset_ms)
                latencies.append(latency_ms)

            if not offsets:
                devices.append(
                    {
                        "device_id": device_id,
                        "probes_ok": 0,
                        "probes_total": attempts,
                        "clock_offset_ms": None,
                        "latency_ms_min": None,
                        "latency_ms_median": None,
                        "latency_ms_max": None,
                        "sync_quality": "bad",
                        "sync_quality_color": "red",
                        "detail": "no clock sync response",
                    }
                )
                continue

            offset_ms = float(statistics.median(offsets))
            lat_min = float(min(latencies))
            lat_median = float(statistics.median(latencies))
            lat_max = float(max(latencies))
            quality = self._classify_quality(offset_ms=offset_ms, latency_ms=lat_median)

            devices.append(
                {
                    "device_id": device_id,
                    "probes_ok": len(offsets),
                    "probes_total": attempts,
                    "clock_offset_ms": round(offset_ms, 3),
                    "latency_ms_min": round(lat_min, 3),
                    "latency_ms_median": round(lat_median, 3),
                    "latency_ms_max": round(lat_max, 3),
                    "sync_quality": quality,
                    "sync_quality_color": self._quality_color(quality),
                    "detail": "ok",
                }
            )

        overall_quality = self._aggregate_quality([item["sync_quality"] for item in devices])
        report = {
            "session_id": session_id,
            "measured_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "devices": devices,
            "overall_sync_quality": overall_quality,
            "overall_sync_quality_color": self._quality_color(overall_quality),
        }
        self.write_sync_report(session_id, report)
        return report

    def enrich_report_with_session_start(
        self,
        *,
        session_id: str,
        authority: SessionTimeAuthority,
        video_start_monotonic_ms: int | None,
    ) -> dict[str, Any]:
        report = self.read_sync_report(session_id)
        report["session_id"] = session_id
        report["server_start_time_unix_ns"] = authority.server_start_time_unix_ns
        report["session_start_monotonic_ms"] = authority.session_start_monotonic_ms
        if video_start_monotonic_ms is not None:
            report["video_start_monotonic_ms"] = video_start_monotonic_ms
            report["video_start_offset_ms"] = int(video_start_monotonic_ms - authority.session_start_monotonic_ms)
        self.write_sync_report(session_id, report)
        return report

    def read_sync_report(self, session_id: str) -> dict[str, Any]:
        path = self._sync_report_path(session_id)
        if not path.exists():
            return {
                "session_id": session_id,
                "devices": [],
                "overall_sync_quality": "unknown",
                "overall_sync_quality_color": "yellow",
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "session_id": session_id,
                "devices": [],
                "overall_sync_quality": "bad",
                "overall_sync_quality_color": "red",
                "detail": "sync_report parse failed",
            }

    def write_sync_report(self, session_id: str, payload: dict[str, Any]) -> Path:
        path = self._sync_report_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return path

    def clear_session(self, session_id: str) -> None:
        self._session_time_authority.pop(session_id, None)

    def _sync_report_path(self, session_id: str) -> Path:
        return self._settings.data_root / "sessions" / session_id / "sync_report.json"

    def _classify_quality(self, *, offset_ms: float, latency_ms: float) -> str:
        abs_offset = abs(offset_ms)
        if abs_offset <= self._settings.clock_sync_good_offset_ms and latency_ms <= self._settings.clock_sync_good_latency_ms:
            return "good"
        if abs_offset <= self._settings.clock_sync_warn_offset_ms and latency_ms <= self._settings.clock_sync_warn_latency_ms:
            return "warning"
        return "bad"

    @staticmethod
    def _quality_color(quality: str) -> str:
        if quality == "good":
            return "green"
        if quality == "warning":
            return "yellow"
        return "red"

    @staticmethod
    def _aggregate_quality(qualities: list[str]) -> str:
        if not qualities:
            return "unknown"
        if "bad" in qualities:
            return "bad"
        if "warning" in qualities:
            return "warning"
        return "good"


clock_sync_service = ClockSyncService()
