"""
Simulates a single IMU mobile node for backend+frontend testing without a phone.
Run from repo root: python tools/device_simulator.py

Sends: DeviceRegister, PING every 1s, SensorPacket at 10Hz on telemetry channel.
Press Ctrl+C to disconnect.
"""
import asyncio
import math
import struct
import time
import uuid

try:
    import websockets
except ImportError:
    raise SystemExit("Run: pip install websockets")

BACKEND = "ws://localhost:8000"
DEVICE_ID = "sim-" + str(uuid.uuid4())[:8]
DEVICE_ROLE = "chest"


# ── Proto binary helpers ──────────────────────────────────────────────────────

def _varint(v: int) -> bytes:
    buf = []
    while v > 0x7F:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    buf.append(v & 0x7F)
    return bytes(buf)


def _str_field(field: int, value: str) -> bytes:
    enc = value.encode()
    return _varint((field << 3) | 2) + _varint(len(enc)) + enc


def _float_field(field: int, value: float) -> bytes:
    return _varint((field << 3) | 5) + struct.pack("<f", value)


def _int_field(field: int, value: int) -> bytes:
    return _varint((field << 3) | 0) + _varint(value)


# ── Message builders ──────────────────────────────────────────────────────────

def build_device_register() -> bytes:
    return (
        _str_field(1, DEVICE_ID) +
        _str_field(2, DEVICE_ROLE) +
        _str_field(3, "Simulator") +
        _str_field(4, "14") +
        _str_field(5, "2.0.0") +
        _int_field(6, 1)        # schema_version
    )


def build_ping(command_id: str) -> bytes:
    # Command: type=PING(0), command_id
    return _int_field(1, 0) + _str_field(4, command_id)


def build_sensor_packet(seq: int) -> bytes:
    t = int(time.time() * 1000)
    theta = seq * 0.1
    return (
        _float_field(1, 0.01 * math.sin(theta)) +      # acc_x
        _float_field(2, -0.02 * math.cos(theta)) +     # acc_y
        _float_field(3, 1.0 + 0.005 * math.sin(theta * 2)) +  # acc_z ≈ 1g
        _float_field(4, 0.5 * math.sin(theta * 0.5)) + # gyro_x
        _float_field(5, -0.3 * math.cos(theta * 0.5)) +# gyro_y
        _float_field(6, 0.1 * math.sin(theta * 0.7)) + # gyro_z
        _int_field(7, t) +          # timestamp_ms
        _int_field(8, seq) +        # sequence_number
        _str_field(9, DEVICE_ID) +  # device_id
        _int_field(10, 1) +         # schema_version
        _int_field(11, t)           # raw_timestamp_ms
    )


# ── Main coroutines ───────────────────────────────────────────────────────────

async def control_loop(ws):
    """Send PING every 1s and print responses."""
    ping_id = 0
    while True:
        cid = f"ping-{ping_id:04d}"
        await ws.send(build_ping(cid))
        ping_id += 1
        await asyncio.sleep(1)


async def telemetry_loop():
    """Stream sensor packets at 10 Hz."""
    async with websockets.connect(f"{BACKEND}/ws/telemetry") as ws:
        seq = 0
        while True:
            await ws.send(build_sensor_packet(seq))
            seq += 1
            await asyncio.sleep(0.1)   # 10 Hz


async def run():
    print(f"Connecting as device_id={DEVICE_ID} role={DEVICE_ROLE}")
    async with websockets.connect(f"{BACKEND}/ws/control") as ctrl:
        await ctrl.send(build_device_register())
        print("✓ DeviceRegister sent — device is now visible in dashboard preflight")
        print("  Starting telemetry at 10 Hz + PING every 1s")
        print("  Press Ctrl+C to disconnect\n")

        await asyncio.gather(
            control_loop(ctrl),
            telemetry_loop(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nSimulator disconnected.")
