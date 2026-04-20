import asyncio
import time

from app.services.ws_runtime import ws_runtime


def test_session_start_countdown_emits_countdown_then_running(monkeypatch) -> None:
    async def _run() -> None:
        events: list[dict[str, object]] = []

        async def _fake_publish(session_id: str, payload: dict[str, object]) -> None:
            await asyncio.sleep(0)
            events.append({"session_id": session_id, **payload})

        monkeypatch.setattr(ws_runtime, "publish_session_event", _fake_publish)

        session_id = "20260419_143022_A1B2C3D4"
        start_at_unix_ns = time.time_ns() + 250_000_000
        await ws_runtime.start_session_countdown(
            session_id=session_id,
            start_at_unix_ns=start_at_unix_ns,
            tick_interval_seconds=0.05,
        )

        await asyncio.sleep(0.45)
        await ws_runtime.stop_session_countdown(session_id)

        countdown_events = [event for event in events if event.get("type") == "SESSION_START_COUNTDOWN"]
        assert countdown_events
        assert any(event.get("status") == "COUNTDOWN" for event in countdown_events)
        assert countdown_events[-1].get("status") == "RUNNING"
        assert int(countdown_events[-1].get("remaining_ms", 1)) == 0

    asyncio.run(_run())


def test_session_start_countdown_stop_cancels_ticker(monkeypatch) -> None:
    async def _run() -> None:
        events: list[dict[str, object]] = []

        async def _fake_publish(session_id: str, payload: dict[str, object]) -> None:
            await asyncio.sleep(0)
            events.append({"session_id": session_id, **payload})

        monkeypatch.setattr(ws_runtime, "publish_session_event", _fake_publish)

        session_id = "20260419_143022_A1B2C3D4"
        start_at_unix_ns = time.time_ns() + 2_000_000_000
        await ws_runtime.start_session_countdown(
            session_id=session_id,
            start_at_unix_ns=start_at_unix_ns,
            tick_interval_seconds=0.05,
        )
        await asyncio.sleep(0.12)
        await ws_runtime.stop_session_countdown(session_id)
        await asyncio.sleep(0.12)

        countdown_events = [event for event in events if event.get("type") == "SESSION_START_COUNTDOWN"]
        assert countdown_events
        assert all(event.get("status") == "COUNTDOWN" for event in countdown_events)

    asyncio.run(_run())
