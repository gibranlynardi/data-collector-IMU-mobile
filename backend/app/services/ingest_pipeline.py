from __future__ import annotations

from typing import Any

from google.protobuf.message import DecodeError
from generated.sensor_sample_pb2 import SensorBatch

from app.core.config import get_settings
from app.services.csv_writer import csv_writer_service


class IngestProtocolError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def ingest_protobuf_batch_message(
    batch: SensorBatch,
    raw_payload: bytes | None = None,
    device_role_override: str | None = None,
) -> dict[str, Any]:
    """Single ingest path for protobuf batches.

    REST ingest and future WS ingest should both call this function so
    dedup, CSV append, gap tracking, and raw binlog archive stay consistent.
    """

    return csv_writer_service.ingest_sensor_batch_proto(
        batch=batch,
        raw_payload=raw_payload,
        device_role_override=device_role_override,
    )


def ingest_ws_binary_batch(
    raw_payload: bytes,
    *,
    connection_session_id: str | None = None,
    connection_device_id: str | None = None,
    device_role_override: str | None = None,
) -> dict[str, Any]:
    """WS adapter for binary SensorBatch frames.

    This keeps WS ACK schema stable while reusing the same ingest path as REST.
    """

    batch = SensorBatch()
    try:
        batch.ParseFromString(raw_payload)
    except DecodeError as exc:
        raise IngestProtocolError(
            code="INVALID_PROTOBUF",
            detail="payload binary tidak bisa diparse sebagai SensorBatch",
        ) from exc

    if not batch.samples:
        raise IngestProtocolError(
            code="EMPTY_BATCH",
            detail="SensorBatch.samples tidak boleh kosong",
        )

    settings = get_settings()
    if len(batch.samples) > settings.ws_max_batch_samples:
        raise IngestProtocolError(
            code="BATCH_LIMIT_EXCEEDED",
            detail=f"sample_count={len(batch.samples)} melebihi limit {settings.ws_max_batch_samples}",
        )

    first_seq = int(batch.samples[0].seq)
    last_seq = int(batch.samples[-1].seq)
    if int(batch.start_seq) != first_seq or int(batch.end_seq) != last_seq:
        raise IngestProtocolError(
            code="BATCH_SEQ_MISMATCH",
            detail="start_seq/end_seq tidak cocok dengan sample boundary",
        )

    prev_seq: int | None = None
    for sample in batch.samples:
        current = int(sample.seq)
        if prev_seq is not None and current <= prev_seq:
            raise IngestProtocolError(
                code="NON_MONOTONIC_SEQ",
                detail="seq sample harus berurutan naik (strictly increasing)",
            )
        prev_seq = current

    if connection_session_id is not None and batch.session_id != connection_session_id:
        raise IngestProtocolError(
            code="SESSION_OR_DEVICE_MISMATCH",
            detail="session_id atau device_id di batch tidak cocok dengan koneksi",
        )

    if connection_device_id is not None and batch.device_id != connection_device_id:
        raise IngestProtocolError(
            code="SESSION_OR_DEVICE_MISMATCH",
            detail="session_id atau device_id di batch tidak cocok dengan koneksi",
        )

    ingest_result = ingest_protobuf_batch_message(
        batch=batch,
        raw_payload=raw_payload,
        device_role_override=device_role_override,
    )

    duplicate = bool(ingest_result.get("written", 0) == 0)

    return {
        "type": "ACK",
        "session_id": batch.session_id,
        "device_id": batch.device_id,
        "batch_start_seq": int(batch.start_seq),
        "batch_end_seq": int(batch.end_seq),
        "last_received_seq": int(ingest_result.get("last_seq", 0) or 0),
        "duplicate": duplicate,
        "duplicate_batches": 1 if duplicate else 0,
    }
