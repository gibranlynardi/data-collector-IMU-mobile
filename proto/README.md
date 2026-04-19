# Protobuf Contract (Phase 1)

Schema package: `imu.collector.v1`

## Files

- `sensor_sample.proto`
- `device_status.proto`
- `control.proto`

## Schema versioning

- Version format: `MAJOR.MINOR.PATCH` (contoh: `1.0.0`).
- Simpan versi schema di metadata session dan pada `ControlCommand.schema_version`.
- Rule compatibility:
  - PATCH: hanya perbaikan non-breaking (komentar, docs, field option non-wire).
  - MINOR: hanya tambah field baru dengan field number baru; tidak mengubah field number lama.
  - MAJOR: perubahan breaking (rename + re-number atau remove field).
- Jangan reuse field number yang sudah pernah dipakai.
- Jika field deprecated, tandai `reserved` sebelum dihapus di major berikutnya.

## Code generation

`protoc` wajib terpasang dan plugin target harus tersedia.

### Dart/Flutter

```bash
c:/Users/antho/OneDrive/Gambar/Dokumen/data-collector-IMU-mobile/.venv/Scripts/python.exe -m grpc_tools.protoc \
  -I proto \
  --plugin=protoc-gen-dart=tools/protoc-gen-dart.cmd \
  --dart_out=mobile-app/lib/generated \
  proto/sensor_sample.proto proto/device_status.proto proto/control.proto
```

### Python/FastAPI

```bash
python -m grpc_tools.protoc \
  -I proto \
  --python_out=backend/generated \
  proto/sensor_sample.proto proto/device_status.proto proto/control.proto
```

## Current status

- Kontrak Proto sudah dibuat.
- Generate code Python sudah ada di `backend/generated/`.
- Generate code Dart sudah ada di `mobile-app/lib/generated/`.

## WS framing policy (official)

- Official transport untuk data dan control adalah **binary Protobuf**.
  - Sensor stream: `SensorBatch` (binary frame).
  - Control command backend -> phone: `ControlCommand` (binary frame).
- JSON text dipertahankan untuk kebutuhan berikut:
  - handshake (`HELLO` / `HELLO_ACK`),
  - heartbeat,
  - backward compatibility saat rollout mobile node,
  - debug messages.
- Implementasi baru harus mengutamakan binary Protobuf untuk command control.
