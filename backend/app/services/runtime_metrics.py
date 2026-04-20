from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.csv_writer import csv_writer_service
from app.services.video_recorder import video_recorder_service
from app.services.ws_runtime import ws_runtime


def _sensor_summary_files() -> list[Path]:
    root = get_settings().data_root / "sessions"
    if not root.exists():
        return []
    return sorted(root.glob("*/sensor/*.summary.json"))


def _gap_size(ranges: list[Any]) -> int:
    total = 0
    for item in ranges:
        if not isinstance(item, list) or len(item) != 2:
            continue
        try:
            start = int(item[0])
            end = int(item[1])
        except Exception:
            continue
        if end < start:
            continue
        total += (end - start) + 1
    return total


async def collect_runtime_metrics() -> dict[str, Any]:
    settings = get_settings()
    ws_metrics = await ws_runtime.collect_runtime_metrics()
    csv_metrics = csv_writer_service.collect_runtime_metrics()

    effective_hz: dict[str, float] = {}
    dropped_gap_samples: dict[str, int] = {}
    for file_path in _sensor_summary_files():
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        session_id = str(payload.get("session_id", "")).strip()
        device_id = str(payload.get("device_id", "")).strip()
        if not session_id or not device_id:
            continue
        key = f"{session_id}:{device_id}"
        effective_hz[key] = float(payload.get("effective_hz", 0.0) or 0.0)
        ranges = payload.get("missing_seq_ranges")
        dropped_gap_samples[key] = _gap_size(ranges if isinstance(ranges, list) else [])

    storage = shutil.disk_usage(settings.data_root)

    metrics: dict[str, Any] = {
        "samples_per_sec_per_device": {k: v.get("samples_per_sec", 0.0) for k, v in ws_metrics.items()},
        "effective_hz_per_device": effective_hz,
        "dropped_gap_samples_per_device": dropped_gap_samples,
        "websocket_reconnect_count_per_device": {k: int(v.get("reconnect_count", 0) or 0) for k, v in ws_metrics.items()},
        "upload_retry_count_per_device": {k: int(v.get("upload_retry_count", 0) or 0) for k, v in ws_metrics.items()},
        "csv_write_latency_ms_per_device": {
            k: {
                "avg": v.get("avg_write_latency_ms", 0.0),
                "max": v.get("max_write_latency_ms", 0.0),
            }
            for k, v in csv_metrics.items()
        },
        "video_fps_runtime": video_recorder_service.collect_runtime_metrics(),
        "storage_free_bytes": int(storage.free),
    }

    return metrics
