"""
IMU Telemetry Backend — FastAPI entry point.
Run: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

from .audit_logger import audit
from .session_manager import session_manager
from .ws_handler import router as ws_router, _live_broadcaster_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _ensure_dirs()
    await _start_audit()
    await _start_mdns()
    _check_interrupted_sessions()
    asyncio.create_task(_live_broadcaster_loop())
    logger.info("IMU Telemetry Backend ready — listening on %s:%s",
                os.getenv("BIND_HOST", "0.0.0.0"), os.getenv("PORT", "8000"))
    yield
    # Shutdown
    await audit.close()
    await _stop_mdns()


app = FastAPI(
    title="IMU Telemetry Backend",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Frontend on same LAN; tighten via LAN_SUBNET if needed
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "session_state": session_manager.state,
        "session_id": session_manager.session_id or None,
        "online_devices": len(session_manager.online_devices),
    }


@app.get("/session")
async def session_info():
    devices = [
        {
            "device_id": d.device_id,
            "role": d.device_role,
            "is_online": d.is_online,
            "packets": d.packets_received,
        }
        for d in session_manager.online_devices
    ]
    return {
        "state": session_manager.state,
        "session_id": session_manager.session_id,
        "subject": session_manager.subject_name,
        "devices": devices,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_dirs():
    for env_key in ("SSD_PATH", "RESCUE_PATH"):
        p = Path(os.getenv(env_key, f"./{env_key.lower()}"))
        p.mkdir(parents=True, exist_ok=True)


async def _start_audit():
    log_path = Path(os.getenv("SSD_PATH", "./data")) / "backend_audit.jsonl"
    await audit.open(log_path)
    await audit.log("INFO", "backend_start", {"version": "2.0.0"})


def _check_interrupted_sessions():
    interrupted = session_manager.get_interrupted_sessions()
    if interrupted:
        logger.warning(
            "Found %d interrupted session(s): %s — recover via /session endpoint",
            len(interrupted),
            [s["session_id"] for s in interrupted],
        )


# mDNS advertisement so Flutter can discover the backend automatically.
_zc = None
_mdns_info = None


async def _start_mdns():
    global _zc, _mdns_info
    try:
        from zeroconf.asyncio import AsyncZeroconf
        from zeroconf import ServiceInfo

        local_ip = _get_local_ip()
        port = int(os.getenv("PORT", "8000"))
        _zc = AsyncZeroconf()
        _mdns_info = ServiceInfo(
            "_imu-telemetry._tcp.local.",
            "IMU Backend._imu-telemetry._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties={"version": "2.0.0"},
        )
        await _zc.async_register_service(_mdns_info)
        logger.info("mDNS registered — ip=%s port=%d", local_ip, port)
    except Exception as exc:
        logger.warning("mDNS registration skipped: %s", exc)


async def _stop_mdns():
    global _zc, _mdns_info
    if _zc and _mdns_info:
        try:
            await _zc.async_unregister_service(_mdns_info)
            await _zc.async_close()
        except Exception:
            pass


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
