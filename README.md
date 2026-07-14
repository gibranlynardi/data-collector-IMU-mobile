# IMU Telemetry System

IMU Telemetry System is a multi-device data collection platform for recording inertial sensor streams from mobile devices and coordinating them from an operator dashboard.

It is split into three main parts:

- `master_backend/` - FastAPI backend, WebSocket hub, session state machine, audit logging, and mDNS discovery.
- `master_frontend/` - Next.js operator dashboard for connection, preflight checks, live charts, labeling, integrity reporting, and multi-camera recording.
- `mobile_node/` - Flutter mobile client that reads device sensors, connects to the backend, and persists session state for recovery.

Shared protobuf contracts live in `shared_contracts/`, while `tools/` contains helper scripts such as the device simulator.

## What this system does

- Collects IMU telemetry from one or more mobile devices.
- Broadcasts session and device state to the dashboard in real time.
- Supports a session flow of `IDLE -> PREFLIGHT -> READY -> RECORDING -> FINALIZING -> VALIDATING -> IDLE`.
- Stores backend audit logs and session artifacts for later review.
- Uses mDNS so Flutter clients can discover the backend automatically on the local network.

## Requirements

- Python 3.10+
- Node.js 18+
- Flutter 3.3+ / Dart 3.3+
- `protoc` if you want to regenerate protobuf bindings

## Quick start

The full setup and runtime order are documented in [STARTUP.md](STARTUP.md). The short version is:

1. Start the backend from the repository root.
2. Start the Next.js dashboard in `master_frontend/`.
3. Open the Flutter app on each phone and connect it to the backend IP or mDNS name.
4. Complete the preflight checklist in the dashboard before starting a recording session.

## Useful commands

From the repository root, the `Makefile` provides a few common tasks:

- `make proto` - regenerate Dart and Python protobuf bindings.
- `make run-backend` - start the FastAPI backend.
- `make run-frontend` - start the operator dashboard.
- `make install-backend` - install backend Python dependencies.
- `make install-frontend` - install frontend Node dependencies.

## Repository layout

- `master_backend/app/` - backend services, WebSocket handlers, session manager, and validation logic.
- `master_frontend/src/` - dashboard UI components and WebSocket client.
- `mobile_node/lib/` - Flutter screens, services, widgets, and models.
- `shared_contracts/` - `.proto` files shared across backend, frontend, and mobile clients.

## Need the full setup?

See [STARTUP.md](STARTUP.md) for environment setup, launch commands, networking notes, and troubleshooting.
