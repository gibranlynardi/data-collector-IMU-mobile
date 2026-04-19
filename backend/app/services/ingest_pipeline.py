from __future__ import annotations

from typing import Any

from generated.sensor_sample_pb2 import SensorBatch

from app.services.csv_writer import csv_writer_service


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
