# Startup Guide

This guide covers the standard setup for the three runtime parts of the system:

- Backend: FastAPI service in `master_backend/`
- Operator dashboard: Next.js app in `master_frontend/`
- Mobile client: Flutter app in `mobile_node/`

The recommended order is backend first, then dashboard, then the phones.

## Prerequisites

- Python 3.10+
- Node.js 18+
- Flutter 3.3+ if you are building or running the mobile client
- `protoc` if you need to regenerate shared protobuf bindings
- Windows with a writable local storage path for session files

## 1. Backend setup

The backend is responsible for session state, WebSocket routing, audit logging, and mDNS discovery.

### First-time setup

```powershell
cd master_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Configure environment

Create the backend environment file:

```powershell
copy .env.example .env
```

Minimum expected values:

```env
SSD_PATH=D:/IMU_Data_SSD
RESCUE_PATH=D:/IMU_Data_Rescue
BIND_HOST=0.0.0.0
PORT=8000
LAN_SUBNET=192.168.1.0/24
FSYNC_INTERVAL_SEC=5
MAX_CONCURRENT_DEVICES=8
```

Create the storage directories if they do not already exist:

```powershell
mkdir D:\IMU_Data_SSD
mkdir D:\IMU_Data_Rescue
```

### Run the backend

Run this from the repository root, not from inside `master_backend/`:

```powershell
master_backend\venv\Scripts\activate
python master_backend/run.py
```

If you prefer to call uvicorn directly:

```powershell
uvicorn master_backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend is ready when it logs that uvicorn is running on port 8000.

### Backend endpoints

- `ws://<laptop-ip>:8000/ws/telemetry` - sensor stream from the mobile client
- `ws://<laptop-ip>:8000/ws/control` - command channel between dashboard and mobile client
- `ws://<laptop-ip>:8000/ws/frontend` - dashboard connection for session state
- `ws://<laptop-ip>:8000/ws/live` - live chart updates for the dashboard

## 2. Frontend setup

The frontend is the operator dashboard. It handles connection, preflight checks, labeling, integrity review, and camera coordination.

### First-time setup

```powershell
cd master_frontend
npm install
```

### Run the dashboard

```powershell
npm run dev
```

Open http://localhost:3000 in your browser.

### Production build

```powershell
npm run build
npm run start
```

## 3. Mobile client setup

The Flutter app reads device sensors and connects to the backend over the local network.

### First-time setup

If you are building the app locally, install Flutter dependencies in `mobile_node/` and make sure the generated protobuf files are present.

### Connection notes

- The app can discover the backend via mDNS when both devices are on the same LAN.
- If discovery fails, enter the laptop IP manually.
- The dashboard preflight should pass before starting a recording session.

## Typical startup order

1. Start the backend first so it can register mDNS and accept WebSocket connections.
2. Start the frontend second so the operator can confirm the session state and preflight checks.
3. Open the Flutter app on each phone and connect it to the backend.
4. Verify the dashboard is ready before starting the recording session.

## Finding the laptop IP

```powershell
ipconfig | findstr "IPv4"
```

Use the IP that is on the same Wi-Fi subnet as the phones, usually something like 192.168.1.x.

## Common issues

| Problem | Fix |
|---------|-----|
| Backend fails with ModuleNotFoundError | Run commands from the repository root or activate the backend virtual environment first |
| Port 8000 already in use | Check which process owns the port and stop it before restarting |
| Frontend cannot connect to backend | Verify the backend is running, the IP is correct, and the firewall allows LAN traffic on port 8000 |
| Flutter cannot discover the backend | Use the manual IP field and confirm both devices are on the same Wi-Fi network |
| SSD_PATH write errors | Create the directory or update the path to a writable location |

## Optional helper commands

The root `Makefile` includes a few shortcuts:

- `make proto` - regenerate Dart and Python protobuf bindings
- `make run-backend` - start the backend
- `make run-frontend` - start the dashboard
- `make install-backend` - install backend dependencies
- `make install-frontend` - install frontend dependencies
