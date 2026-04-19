import asyncio
from datetime import UTC, datetime

from app.core.config import get_settings
from app.services.clock_sync import clock_sync_service


def test_run_preflight_sync_classifies_quality_and_writes_report(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    clock_sync_service._settings = get_settings()

    async def _fake_probe(_session_id: str, device_id: str, timeout_seconds: float):
        del timeout_seconds
        if device_id == "DEVICE-CHEST-001":
            return {
                "server_send_unix_ns": 1_000_000_000,
                "server_recv_unix_ns": 1_020_000_000,
                "device_unix_ns": 1_010_000_000,
            }
        return None

    monkeypatch.setattr("app.services.clock_sync.ws_runtime.request_clock_sync_probe", _fake_probe)

    report = asyncio.run(
        clock_sync_service.run_preflight_sync(
            session_id="20260419_143022_A1B2C3D4",
            device_ids=["DEVICE-CHEST-001", "DEVICE-WAIST-001"],
        )
    )

    assert report["overall_sync_quality"] in {"warning", "bad"}
    assert len(report["devices"]) == 2
    chest = next(item for item in report["devices"] if item["device_id"] == "DEVICE-CHEST-001")
    assert chest["clock_offset_ms"] is not None
    waist = next(item for item in report["devices"] if item["device_id"] == "DEVICE-WAIST-001")
    assert waist["sync_quality"] == "bad"

    path = data_root / "sessions" / "20260419_143022_A1B2C3D4" / "sync_report.json"
    assert path.exists()


def test_enrich_report_with_session_start_and_video_offset(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    clock_sync_service._settings = get_settings()

    session_id = "20260419_143022_A1B2C3D4"
    authority = clock_sync_service.mark_session_started(session_id, datetime.now(UTC).replace(tzinfo=None))
    report = clock_sync_service.enrich_report_with_session_start(
        session_id=session_id,
        authority=authority,
        video_start_monotonic_ms=authority.session_start_monotonic_ms + 55,
    )

    assert report["server_start_time_unix_ns"] == authority.server_start_time_unix_ns
    assert report["session_start_monotonic_ms"] == authority.session_start_monotonic_ms
    assert report["video_start_offset_ms"] == 55
