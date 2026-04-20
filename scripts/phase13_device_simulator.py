#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import websockets

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generated.sensor_sample_pb2 import SensorBatch, SensorSample  # noqa: E402


def _http_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


@dataclass
class SimDevice:
    device_id: str
    device_role: str
    ws_base: str
    session_id: str
    hz: int
    duration_seconds: int
    disconnect_at_seconds: int | None = None
    reconnect_delay_seconds: int = 3

    async def run(self) -> None:
        local_last_seq = 0
        started = time.monotonic()
        disconnected_once = False

        while True:
            elapsed = time.monotonic() - started
            if elapsed >= self.duration_seconds:
                return

            uri = f"{self.ws_base}/ws/device/{self.device_id}"
            try:
                async with websockets.connect(uri, max_size=8_388_608) as ws:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "HELLO",
                                "device_id": self.device_id,
                                "device_role": self.device_role,
                                "session_id": self.session_id,
                                "local_last_seq": local_last_seq,
                            },
                            ensure_ascii=True,
                        )
                    )
                    hello_ack = json.loads(await ws.recv())
                    if hello_ack.get("type") != "HELLO_ACK":
                        raise RuntimeError(f"HELLO_ACK expected, got {hello_ack}")

                    send_interval = 1.0 / float(max(1, self.hz))
                    phase = random.random() * math.pi
                    while True:
                        now_elapsed = time.monotonic() - started
                        if now_elapsed >= self.duration_seconds:
                            return

                        if (
                            self.disconnect_at_seconds is not None
                            and not disconnected_once
                            and now_elapsed >= self.disconnect_at_seconds
                        ):
                            disconnected_once = True
                            await ws.close()
                            await asyncio.sleep(self.reconnect_delay_seconds)
                            break

                        local_last_seq += 1
                        sample = SensorSample(
                            session_id=self.session_id,
                            device_id=self.device_id,
                            device_role=self.device_role,
                            seq=local_last_seq,
                            timestamp_device_unix_ns=time.time_ns(),
                            elapsed_ms=int(now_elapsed * 1000),
                            acc_x_g=0.1 * math.sin(phase + local_last_seq * 0.1),
                            acc_y_g=0.1 * math.cos(phase + local_last_seq * 0.1),
                            acc_z_g=1.0,
                            gyro_x_deg=2.0,
                            gyro_y_deg=1.5,
                            gyro_z_deg=1.0,
                        )
                        batch = SensorBatch(
                            session_id=self.session_id,
                            device_id=self.device_id,
                            start_seq=local_last_seq,
                            end_seq=local_last_seq,
                            samples=[sample],
                        )
                        await ws.send(batch.SerializeToString())

                        try:
                            ack_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            if isinstance(ack_raw, str):
                                ack = json.loads(ack_raw)
                                if ack.get("type") != "ACK":
                                    print(f"[{self.device_id}] non-ACK message: {ack}")
                        except asyncio.TimeoutError:
                            print(f"[{self.device_id}] ACK timeout")

                        await asyncio.sleep(send_interval)
            except Exception as exc:
                print(f"[{self.device_id}] connection error: {exc}; retrying in 1s")
                await asyncio.sleep(1)


def _register_devices(rest_base: str) -> None:
    devices = [
        ("DEVICE-CHEST-001", "chest"),
        ("DEVICE-WAIST-001", "waist"),
        ("DEVICE-THIGH-001", "thigh"),
    ]
    for device_id, role in devices:
        _http_json(
            "POST",
            f"{rest_base}/devices/register",
            {
                "device_id": device_id,
                "device_role": role,
                "display_name": f"Simulator {role}",
                "ip_address": "127.0.0.1",
            },
        )


def _setup_session(rest_base: str, session_id: str | None) -> str:
    if session_id:
        sid = session_id
    else:
        created = _http_json(
            "POST",
            f"{rest_base}/sessions",
            {
                "override_reason": "phase13 simulator run",
            },
        )
        sid = str(created["session_id"])

    _http_json(
        "PUT",
        f"{rest_base}/sessions/{sid}/devices",
        {
            "assignments": [
                {"device_id": "DEVICE-CHEST-001", "required": True},
                {"device_id": "DEVICE-WAIST-001", "required": True},
                {"device_id": "DEVICE-THIGH-001", "required": True},
            ],
            "replace": True,
        },
    )
    return sid


def _start_session(rest_base: str, session_id: str) -> None:
    try:
        _http_json("POST", f"{rest_base}/sessions/{session_id}/start")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"start session failed (continuing): HTTP {exc.code} {body}")


def _stop_session(rest_base: str, session_id: str) -> None:
    try:
        _http_json("POST", f"{rest_base}/sessions/{session_id}/stop")
    except Exception as exc:
        print(f"stop session warning: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 13 device simulator (3 devices, 100Hz, disconnect/reconnect)")
    parser.add_argument("--rest-base", default="http://127.0.0.1:8000", help="Backend REST base URL")
    parser.add_argument("--ws-base", default="ws://127.0.0.1:8001", help="Backend WS base URL")
    parser.add_argument("--session-id", default="", help="Existing session_id to use; empty means create new")
    parser.add_argument("--hz", type=int, default=100, help="Sampling frequency per device")
    parser.add_argument("--duration-seconds", type=int, default=20, help="Simulation duration")
    parser.add_argument("--skip-start", action="store_true", help="Skip calling start session")
    parser.add_argument("--skip-stop", action="store_true", help="Skip calling stop session")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    _register_devices(args.rest_base)
    session_id = _setup_session(args.rest_base, args.session_id or None)
    if not args.skip_start:
        _start_session(args.rest_base, session_id)

    print(f"Running simulator for session {session_id}")

    devices = [
        SimDevice("DEVICE-CHEST-001", "chest", args.ws_base, session_id, args.hz, args.duration_seconds),
        SimDevice("DEVICE-WAIST-001", "waist", args.ws_base, session_id, args.hz, args.duration_seconds),
        SimDevice(
            "DEVICE-THIGH-001",
            "thigh",
            args.ws_base,
            session_id,
            args.hz,
            args.duration_seconds,
            disconnect_at_seconds=max(3, args.duration_seconds // 3),
            reconnect_delay_seconds=3,
        ),
    ]

    await asyncio.gather(*(device.run() for device in devices))

    if not args.skip_stop:
        _stop_session(args.rest_base, session_id)

    print("Phase 13 simulation completed")
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
