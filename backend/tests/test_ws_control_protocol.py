import asyncio

from generated.control_pb2 import ControlCommand, ControlCommandType

from app.services.ws_runtime import ws_runtime


class _FakeWebSocket:
    def __init__(self) -> None:
        self.binary_frames: list[bytes] = []
        self.text_frames: list[str] = []

    async def send_bytes(self, payload: bytes) -> None:
        await asyncio.sleep(0)
        self.binary_frames.append(payload)

    async def send_text(self, payload: str) -> None:
        await asyncio.sleep(0)
        self.text_frames.append(payload)


def test_encode_control_command_start_session() -> None:
    payload = {
        "type": "START_SESSION",
        "session_id": "20260419_143022_A1B2C3D4",
        "server_start_time_unix_ns": 1_700_000_000_000_000_000,
        "recording_start_seq": 1,
        "target_sampling_hz": 100,
        "command_id": "cmd-start-1",
    }

    encoded = ws_runtime._encode_control_command(payload)
    assert encoded is not None

    command = ControlCommand()
    command.ParseFromString(encoded)
    assert command.command == ControlCommandType.START_SESSION
    assert command.session_id == payload["session_id"]
    assert command.server_start_time_unix_ns == payload["server_start_time_unix_ns"]
    assert command.recording_start_seq == payload["recording_start_seq"]
    assert command.target_sampling_hz == payload["target_sampling_hz"]
    assert command.command_id == payload["command_id"]


def test_broadcast_control_uses_binary_frames() -> None:
    async def _run() -> None:
        session_id = "20260419_143022_A1B2C3D4"
        device_id = "DEVICE-CHEST-001"
        ws = _FakeWebSocket()

        async with ws_runtime._lock:
            ws_runtime._device_connections[device_id] = ws
            ws_runtime._device_session_map[device_id] = session_id

        try:
            sent = await ws_runtime.broadcast_command_to_session_devices(
                session_id,
                {
                    "type": "STOP_SESSION",
                    "session_id": session_id,
                    "command_id": "cmd-stop-1",
                },
            )
        finally:
            async with ws_runtime._lock:
                ws_runtime._device_connections.pop(device_id, None)
                ws_runtime._device_session_map.pop(device_id, None)

        assert sent == [device_id]
        assert len(ws.binary_frames) == 1
        assert ws.text_frames == []

        command = ControlCommand()
        command.ParseFromString(ws.binary_frames[0])
        assert command.command == ControlCommandType.STOP_SESSION
        assert command.command_id == "cmd-stop-1"

    asyncio.run(_run())
