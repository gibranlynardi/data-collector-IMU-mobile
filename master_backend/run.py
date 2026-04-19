"""
Dev runner — run from repo root: python master_backend/run.py
Or: uvicorn master_backend.app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "master_backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
