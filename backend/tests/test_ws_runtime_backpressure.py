import asyncio
from contextlib import suppress

from app.services.ws_runtime import DashboardConnection, WsRuntime


async def _run_broadcast_preview_drop_warning_non_blocking() -> None:
    runtime = WsRuntime()
    session_id = "20260419_143022_A1B2C3D4"

    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
    queue.put_nowait({"type": "SATURATED"})

    sender_task = asyncio.create_task(asyncio.sleep(60))
    try:
        runtime._dashboard_connections[session_id] = [
            DashboardConnection(
                websocket=object(),
                queue=queue,
                sender_task=sender_task,
            )
        ]

        await asyncio.wait_for(
            runtime._broadcast(
                session_id,
                {
                    "type": "SENSOR_PREVIEW",
                    "session_id": session_id,
                    "device_id": "DEVICE-CHEST-001",
                    "start_seq": 1,
                    "end_seq": 2,
                    "preview": {"sample_count": 2},
                },
                drop_if_busy=True,
            ),
            timeout=0.2,
        )

        assert queue.qsize() == 1
        assert queue.get_nowait()["type"] == "SATURATED"
    finally:
        sender_task.cancel()
        with suppress(asyncio.CancelledError):
            await sender_task


def test_broadcast_preview_drop_warning_non_blocking() -> None:
    asyncio.run(_run_broadcast_preview_drop_warning_non_blocking())
