# IMU Collector Backend (Phase 2 Foundation)

Backend ini adalah pondasi FastAPI untuk:

- registry device
- lifecycle session
- annotation CRUD
- endpoint artifact metadata
- startup preflight checks
- metadata persistence (SQLite untuk MVP)
- CSV writer append-only per device (Phase 4)

## Phase 4 CSV Writer

- Writer path: `DATA_ROOT/sessions/{session_id}/sensor/{device_role}_{device_id}.csv`
- Header final mengikuti kontrak dataset Phase 4.
- Sidecar files:
	- `{device_role}_{device_id}.state.json` untuk crash recovery state (`last_seq`, missing range, duplicate count).
	- `{device_role}_{device_id}.summary.json` untuk ringkasan final (`first_seq`, `last_seq`, `sample_count`, `effective_hz`).
	- `{device_role}_{device_id}.lock` sebagai lock aktif writer.
	- `{device_role}_{device_id}.binlog` raw protobuf archive (length-prefixed frame).
	- `{device_role}_{device_id}.binlog.index.jsonl` index per batch (`offset`, `payload_size`, seq range).
- Flush policy configurable lewat env:
	- `CSV_FLUSH_EVERY_SAMPLES` (default `200`)
	- `CSV_FLUSH_EVERY_SECONDS` (default `2.0`)
	- `CSV_ALLOW_RECOVER_STALE_LOCK` (default `true`)

### Ingest endpoint (MVP backend)

`POST /sessions/{session_id}/ingest/sensor-batch`

- menerima payload JSON samples per batch.
- validasi session status hanya `RUNNING` atau `ENDING`.
- duplicate seq otomatis skip.
- gap seq otomatis dicatat di state/summary.
- raw protobuf payload otomatis di-append ke `.binlog` untuk audit/debug.

### Hook untuk branch WS

Saat branch WebSocket digabung, handler batch device cukup memanggil satu fungsi ini:

`app.services.ingest_pipeline.ingest_protobuf_batch_message(batch, raw_payload=payload_bytes)`

Dengan ini jalur ingest REST dan WS tetap tunggal (dedup, CSV append, gap tracking, dan raw archive konsisten).

## Quickstart

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\activate
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment

Copy `.env.example` ke `.env` jika perlu override default.

## Metadata storage

- MVP: SQLite local database di `DATA_ROOT/metadata.db`
- Future: pindah ke PostgreSQL/TimescaleDB lewat `DATABASE_URL`
