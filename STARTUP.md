# Startup Guide — Backend & Frontend

## Prerequisites

- Python 3.10+
- Node.js 18+ / npm
- Windows (paths use `D:/` — adjust if different)

---

## Backend (FastAPI)

### 1. First-time setup

```powershell
cd master_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```powershell
copy .env.example .env
```

Edit `.env` — minimum required:

```env
SSD_PATH=D:/IMU_Data_SSD        # where session CSVs are written
RESCUE_PATH=D:/IMU_Data_Rescue  # fallback if SSD disconnects
BIND_HOST=0.0.0.0
PORT=8000
LAN_SUBNET=192.168.1.0/24       # restrict to your local network
FSYNC_INTERVAL_SEC=5
MAX_CONCURRENT_DEVICES=8
```

Create the storage directories if they don't exist:

```powershell
mkdir D:\IMU_Data_SSD
mkdir D:\IMU_Data_Rescue
```

### 3. Run

From the **repo root** (not inside `master_backend/`):

```powershell
# activate venv first
master_backend\venv\Scripts\activate

# Option A — dev runner with auto-reload
python master_backend/run.py

# Option B — direct uvicorn
uvicorn master_backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend is ready when you see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

WebSocket endpoints:
- `ws://<laptop-ip>:8000/ws/telemetry` — sensor data stream (Flutter)
- `ws://<laptop-ip>:8000/ws/control` — command channel (Frontend ↔ Flutter)

---

## Frontend (Next.js)

### 1. First-time setup

```powershell
cd master_frontend
npm install
```

### 2. Run

```powershell
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

For production build:

```powershell
npm run build
npm run start
```

---

## Typical startup order

1. Start **backend** first — it advertises itself via mDNS so Flutter can discover it.
2. Start **frontend** — connects to backend WebSocket automatically.
3. Open the Flutter app on each phone — it scans mDNS or enter the laptop IP manually.
4. Follow the **Preflight checklist** in the UI before starting any recording session.

---

## Finding your laptop IP (for Flutter manual pairing)

```powershell
ipconfig | findstr "IPv4"
```

Use the IP on the same Wi-Fi subnet as the phones (e.g., `192.168.1.x`).

---

## Common issues

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` on backend start | Run from repo root, not from inside `master_backend/` |
| Port 8000 already in use | `netstat -ano \| findstr :8000` → kill the PID |
| Frontend can't reach backend | Check firewall allows port 8000 inbound on the LAN interface |
| Flutter can't find server via mDNS | Enter laptop IP manually in the app; check Wi-Fi isolation on router |
| `SSD_PATH` write error on first run | Create the directory or update `.env` to an existing writable path |
