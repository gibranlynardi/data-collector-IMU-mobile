from __future__ import annotations

import csv
import json
import os
import shutil
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Device, SessionDevice
from generated.sensor_sample_pb2 import SensorBatch

CSV_HEADER = [
    "session_id",
    "device_id",
    "device_role",
    "seq",
    "timestamp_device_unix_ns",
    "timestamp_server_unix_ns",
    "estimated_server_unix_ns",
    "elapsed_ms",
    "acc_x_g",
    "acc_y_g",
    "acc_z_g",
    "gyro_x_deg",
    "gyro_y_deg",
    "gyro_z_deg",
]


@dataclass
class SensorSampleRow:
    session_id: str
    device_id: str
    device_role: str
    seq: int
    timestamp_device_unix_ns: int
    elapsed_ms: int
    acc_x_g: float
    acc_y_g: float
    acc_z_g: float
    gyro_x_deg: float
    gyro_y_deg: float
    gyro_z_deg: float


@dataclass
class DeviceWriterState:
    session_id: str
    device_id: str
    device_role: str
    csv_path: Path
    state_path: Path
    summary_path: Path
    lock_path: Path
    binlog_path: Path
    binlog_index_path: Path
    file_obj: Any
    binlog_file_obj: Any
    binlog_index_file_obj: Any
    writer: csv.writer
    first_seq: int | None = None
    last_seq: int | None = None
    sample_count: int = 0
    duplicate_count: int = 0
    missing_ranges: list[list[int]] = field(default_factory=list)
    first_estimated_server_unix_ns: int | None = None
    last_estimated_server_unix_ns: int | None = None
    pending_since_flush: int = 0
    pending_raw_since_flush: int = 0
    last_flush_monotonic: float = field(default_factory=time.monotonic)
    raw_batch_count: int = 0
    raw_total_bytes: int = 0


class CsvWriterService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = threading.RLock()
        self._writers: dict[tuple[str, str], DeviceWriterState] = {}

    def prepare_session_writers(self, db: Session, session_id: str) -> list[str]:
        prepared: list[str] = []

        session_devices = (
            db.query(SessionDevice, Device)
            .join(Device, SessionDevice.device_id == Device.device_id)
            .filter(SessionDevice.session_id == session_id)
            .all()
        )

        if session_devices:
            for session_device, device in session_devices:
                device_role = (device.device_role or "other").lower()
                self.ensure_writer(session_id, session_device.device_id, device_role)
                prepared.append(session_device.device_id)
            return prepared

        devices = db.query(Device).order_by(Device.device_id.asc()).all()
        for device in devices:
            device_role = (device.device_role or "other").lower()
            self.ensure_writer(session_id, device.device_id, device_role)
            prepared.append(device.device_id)
        return prepared

    def ensure_writer(self, session_id: str, device_id: str, device_role: str) -> None:
        key = (session_id, device_id)
        with self._lock:
            if key in self._writers:
                return

            session_root = self._settings.data_root / "sessions" / session_id
            sensor_dir = session_root / "sensor"
            sensor_dir.mkdir(parents=True, exist_ok=True)

            csv_path = sensor_dir / f"{device_role}_{device_id}.csv"
            state_path = sensor_dir / f"{device_role}_{device_id}.state.json"
            summary_path = sensor_dir / f"{device_role}_{device_id}.summary.json"
            lock_path = sensor_dir / f"{device_role}_{device_id}.lock"
            binlog_path = sensor_dir / f"{device_role}_{device_id}.binlog"
            binlog_index_path = sensor_dir / f"{device_role}_{device_id}.binlog.index.jsonl"

            self._acquire_lock(lock_path)

            file_exists = csv_path.exists()
            file_obj = csv_path.open("a", newline="", encoding="utf-8")
            binlog_file_obj = binlog_path.open("ab")
            binlog_index_file_obj = binlog_index_path.open("a", encoding="utf-8")
            writer = csv.writer(file_obj)
            if not file_exists:
                writer.writerow(CSV_HEADER)
                file_obj.flush()

            state = DeviceWriterState(
                session_id=session_id,
                device_id=device_id,
                device_role=device_role,
                csv_path=csv_path,
                state_path=state_path,
                summary_path=summary_path,
                lock_path=lock_path,
                binlog_path=binlog_path,
                binlog_index_path=binlog_index_path,
                file_obj=file_obj,
                binlog_file_obj=binlog_file_obj,
                binlog_index_file_obj=binlog_index_file_obj,
                writer=writer,
            )
            self._hydrate_state_from_disk(state)
            self._writers[key] = state
            self._write_state_file(state)

    def ingest_sensor_batch_proto(
        self,
        batch: SensorBatch,
        device_role_override: str | None = None,
        raw_payload: bytes | None = None,
    ) -> dict[str, Any]:
        session_id = batch.session_id
        device_id = batch.device_id
        device_role = self._resolve_device_role(batch, device_role_override)

        rows: list[SensorSampleRow] = []
        for sample in batch.samples:
            rows.append(
                SensorSampleRow(
                    session_id=session_id,
                    device_id=device_id,
                    device_role=device_role,
                    seq=int(sample.seq),
                    timestamp_device_unix_ns=int(sample.timestamp_device_unix_ns),
                    elapsed_ms=int(sample.elapsed_ms),
                    acc_x_g=float(sample.acc_x_g),
                    acc_y_g=float(sample.acc_y_g),
                    acc_z_g=float(sample.acc_z_g),
                    gyro_x_deg=float(sample.gyro_x_deg),
                    gyro_y_deg=float(sample.gyro_y_deg),
                    gyro_z_deg=float(sample.gyro_z_deg),
                )
            )

        ingest_result = self.ingest_samples(
            session_id=session_id,
            device_id=device_id,
            device_role=device_role,
            samples=rows,
        )

        payload = raw_payload if raw_payload is not None else batch.SerializeToString()
        raw_result = self.append_raw_batch(
            session_id=session_id,
            device_id=device_id,
            device_role=device_role,
            payload=payload,
            start_seq=int(batch.start_seq),
            end_seq=int(batch.end_seq),
            sample_count=len(batch.samples),
        )
        return {
            **ingest_result,
            **raw_result,
        }

    def append_raw_batch(
        self,
        session_id: str,
        device_id: str,
        device_role: str,
        payload: bytes,
        start_seq: int,
        end_seq: int,
        sample_count: int,
    ) -> dict[str, Any]:
        self.ensure_writer(session_id, device_id, device_role)
        key = (session_id, device_id)

        with self._lock:
            state = self._writers[key]
            offset = state.binlog_file_obj.tell()
            payload_size = len(payload)

            # Each frame is length-prefixed so replay/debug tools can iterate safely.
            state.binlog_file_obj.write(struct.pack("<I", payload_size))
            state.binlog_file_obj.write(payload)

            index_row = {
                "session_id": session_id,
                "device_id": device_id,
                "device_role": device_role,
                "offset": offset,
                "payload_size": payload_size,
                "start_seq": start_seq,
                "end_seq": end_seq,
                "sample_count": sample_count,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
            state.binlog_index_file_obj.write(json.dumps(index_row, ensure_ascii=True) + "\n")

            state.raw_batch_count += 1
            state.raw_total_bytes += payload_size
            state.pending_raw_since_flush += 1
            self._flush_if_due(state)
            self._write_state_file(state)

            return {
                "raw_archived": True,
                "raw_payload_size": payload_size,
                "raw_batch_count": state.raw_batch_count,
                "raw_total_bytes": state.raw_total_bytes,
            }

    def ingest_samples(self, session_id: str, device_id: str, device_role: str, samples: list[SensorSampleRow]) -> dict[str, Any]:
        if not samples:
            return {
                "written": 0,
                "duplicates": 0,
                "last_seq": self.get_last_seq(session_id, device_id),
                "missing_ranges": [],
            }

        self.ensure_writer(session_id, device_id, device_role)
        key = (session_id, device_id)

        with self._lock:
            state = self._writers[key]
            written = 0
            duplicates = 0
            gaps_before = len(state.missing_ranges)

            batch_received_server_unix_ns = time.time_ns()
            last_elapsed_ms = samples[-1].elapsed_ms

            for sample in samples:
                if state.last_seq is not None and sample.seq <= state.last_seq:
                    duplicates += 1
                    state.duplicate_count += 1
                    continue

                if state.last_seq is not None and sample.seq > state.last_seq + 1:
                    state.missing_ranges.append([state.last_seq + 1, sample.seq - 1])

                estimated_server_unix_ns = batch_received_server_unix_ns - ((last_elapsed_ms - sample.elapsed_ms) * 1_000_000)

                if state.first_seq is None:
                    state.first_seq = sample.seq
                    state.first_estimated_server_unix_ns = estimated_server_unix_ns

                state.last_seq = sample.seq
                state.last_estimated_server_unix_ns = estimated_server_unix_ns
                state.sample_count += 1
                state.pending_since_flush += 1

                state.writer.writerow(
                    [
                        sample.session_id,
                        sample.device_id,
                        sample.device_role,
                        sample.seq,
                        sample.timestamp_device_unix_ns,
                        batch_received_server_unix_ns,
                        estimated_server_unix_ns,
                        sample.elapsed_ms,
                        sample.acc_x_g,
                        sample.acc_y_g,
                        sample.acc_z_g,
                        sample.gyro_x_deg,
                        sample.gyro_y_deg,
                        sample.gyro_z_deg,
                    ]
                )
                written += 1

            self._flush_if_due(state)
            self._write_state_file(state)

            return {
                "written": written,
                "duplicates": duplicates,
                "last_seq": state.last_seq,
                "missing_ranges_added": len(state.missing_ranges) - gaps_before,
            }

    def flush_session(self, session_id: str) -> None:
        with self._lock:
            for key, state in self._writers.items():
                if key[0] != session_id:
                    continue
                self._flush(state)
                self._write_state_file(state)

    def close_session(self, session_id: str) -> None:
        with self._lock:
            keys = [key for key in self._writers if key[0] == session_id]
            for key in keys:
                state = self._writers.pop(key)
                self._flush(state)
                state.file_obj.close()
                state.binlog_file_obj.close()
                state.binlog_index_file_obj.close()
                self._write_state_file(state)
                self._write_summary_file(state)
                self._release_lock(state.lock_path)

    def close_all(self) -> None:
        with self._lock:
            keys = list(self._writers.keys())
            for key in keys:
                session_id, _device_id = key
                self.close_session(session_id)

    def get_last_seq(self, session_id: str, device_id: str) -> int:
        with self._lock:
            state = self._writers.get((session_id, device_id))
            if not state or state.last_seq is None:
                return 0
            return state.last_seq

    def _flush_if_due(self, state: DeviceWriterState) -> None:
        now = time.monotonic()
        flush_by_samples = state.pending_since_flush >= self._settings.csv_flush_every_samples
        flush_by_time = (now - state.last_flush_monotonic) >= self._settings.csv_flush_every_seconds
        if flush_by_samples or flush_by_time:
            self._flush(state)

    @staticmethod
    def _flush(state: DeviceWriterState) -> None:
        state.file_obj.flush()
        os.fsync(state.file_obj.fileno())
        state.binlog_file_obj.flush()
        os.fsync(state.binlog_file_obj.fileno())
        state.binlog_index_file_obj.flush()
        os.fsync(state.binlog_index_file_obj.fileno())
        state.pending_since_flush = 0
        state.pending_raw_since_flush = 0
        state.last_flush_monotonic = time.monotonic()

    @staticmethod
    def _resolve_device_role(batch: SensorBatch, device_role_override: str | None) -> str:
        if device_role_override:
            return device_role_override.lower()
        if batch.samples:
            sample_role = str(batch.samples[-1].device_role or "other")
            return sample_role.lower()
        return "other"

    def _acquire_lock(self, lock_path: Path) -> None:
        if lock_path.exists():
            if self._settings.csv_allow_recover_stale_lock:
                stale_name = lock_path.with_suffix(f".stale.{int(time.time())}.lock")
                shutil.move(str(lock_path), str(stale_name))
            else:
                raise RuntimeError(f"writer lock exists: {lock_path}")

        payload = {
            "pid": os.getpid(),
            "acquired_at": datetime.now(UTC).isoformat(),
        }
        lock_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _release_lock(lock_path: Path) -> None:
        if lock_path.exists():
            lock_path.unlink()

    def _hydrate_state_from_disk(self, state: DeviceWriterState) -> None:
        if not state.state_path.exists():
            return

        payload = json.loads(state.state_path.read_text(encoding="utf-8"))
        state.first_seq = payload.get("first_seq")
        state.last_seq = payload.get("last_seq")
        state.sample_count = int(payload.get("sample_count", 0) or 0)
        state.duplicate_count = int(payload.get("duplicate_count", 0) or 0)
        state.missing_ranges = payload.get("missing_ranges", [])
        state.first_estimated_server_unix_ns = payload.get("first_estimated_server_unix_ns")
        state.last_estimated_server_unix_ns = payload.get("last_estimated_server_unix_ns")
        state.raw_batch_count = int(payload.get("raw_batch_count", 0) or 0)
        state.raw_total_bytes = int(payload.get("raw_total_bytes", 0) or 0)

    def _write_state_file(self, state: DeviceWriterState) -> None:
        payload = {
            "session_id": state.session_id,
            "device_id": state.device_id,
            "device_role": state.device_role,
            "csv_path": str(state.csv_path),
            "first_seq": state.first_seq,
            "last_seq": state.last_seq,
            "sample_count": state.sample_count,
            "duplicate_count": state.duplicate_count,
            "missing_ranges": state.missing_ranges,
            "first_estimated_server_unix_ns": state.first_estimated_server_unix_ns,
            "last_estimated_server_unix_ns": state.last_estimated_server_unix_ns,
            "raw_binlog_path": str(state.binlog_path),
            "raw_binlog_index_path": str(state.binlog_index_path),
            "raw_batch_count": state.raw_batch_count,
            "raw_total_bytes": state.raw_total_bytes,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        state.state_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _write_summary_file(self, state: DeviceWriterState) -> None:
        effective_hz = 0.0
        if (
            state.sample_count > 1
            and state.first_estimated_server_unix_ns is not None
            and state.last_estimated_server_unix_ns is not None
            and state.last_estimated_server_unix_ns > state.first_estimated_server_unix_ns
        ):
            duration_sec = (state.last_estimated_server_unix_ns - state.first_estimated_server_unix_ns) / 1_000_000_000
            effective_hz = state.sample_count / duration_sec if duration_sec > 0 else 0.0

        summary = {
            "session_id": state.session_id,
            "device_id": state.device_id,
            "device_role": state.device_role,
            "csv_path": str(state.csv_path),
            "first_seq": state.first_seq,
            "last_seq": state.last_seq,
            "sample_count": state.sample_count,
            "duplicate_count": state.duplicate_count,
            "missing_seq_ranges": state.missing_ranges,
            "effective_hz": round(effective_hz, 3),
            "raw_binlog_path": str(state.binlog_path),
            "raw_binlog_index_path": str(state.binlog_index_path),
            "raw_batch_count": state.raw_batch_count,
            "raw_total_bytes": state.raw_total_bytes,
            "finalized_at": datetime.now(UTC).isoformat(),
        }
        state.summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")


csv_writer_service = CsvWriterService()
