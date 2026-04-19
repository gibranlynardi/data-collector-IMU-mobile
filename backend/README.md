# IMU Collector Backend (Phase 2 Foundation)

Backend ini adalah pondasi FastAPI untuk:

- registry device
- lifecycle session
- annotation CRUD
- endpoint artifact metadata
- startup preflight checks
- metadata persistence (SQLite untuk MVP)

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
