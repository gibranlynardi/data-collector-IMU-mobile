import json
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routers.ws as ws_router
import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel, SessionDevice
from app.services.csv_writer import csv_writer_service
from app.services.ws_runtime import ws_runtime
from generated.sensor_sample_pb2 import SensorBatch


@pytest.fixture()
def session_factory(tmp_path, monkeypatch) -> Iterator[sessionmaker]:
    db_file = tmp_path / "test-metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    csv_writer_service.close_all()
    csv_writer_service._settings = get_settings()
    ws_runtime._settings = get_settings()

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    ws_router.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)
    try:
        yield testing_session_local
    finally:
        csv_writer_service.close_all()
        engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker) -> Iterator[TestClient]:
    with TestClient(main_app.app) as test_client:
        yield test_client


@pytest.fixture()
def seeded_device_session(session_factory: sessionmaker) -> tuple[str, str]:
    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with session_factory() as db:
        db.add(
            Device(
                device_id=device_id,
                device_role="chest",
                display_name="Chest Phone",
                ip_address="192.168.1.10",
                connected=False,
            )
        )
        db.add(
            SessionModel(
                session_id=session_id,
                status="RUNNING",
                preflight_passed=True,
            )
        )
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    return session_id, device_id


def _hello_payload(session_id: str, device_id: str, local_last_seq: int = 0) -> str:
    return json.dumps(
        {
            "type": "HELLO",
            "session_id": session_id,
            "device_id": device_id,
            "device_role": "chest",
            "local_last_seq": local_last_seq,
        }
    )


def _build_sensor_batch(session_id: str, device_id: str, start_seq: int, end_seq: int) -> bytes:
    batch = SensorBatch(
        session_id=session_id,
        device_id=device_id,
        start_seq=start_seq,
        end_seq=end_seq,
    )
    for seq in range(start_seq, end_seq + 1):
        sample = batch.samples.add()
        sample.session_id = session_id
        sample.device_id = device_id
        sample.device_role = "chest"
        sample.seq = seq
        sample.timestamp_device_unix_ns = 1713511822000000000 + seq
        sample.elapsed_ms = seq * 10
        sample.acc_x_g = 0.1
        sample.acc_y_g = 0.2
        sample.acc_z_g = 0.3
        sample.gyro_x_deg = 1.0
        sample.gyro_y_deg = 2.0
        sample.gyro_z_deg = 3.0
    return batch.SerializeToString()


def test_ws_device_handshake(client: TestClient, seeded_device_session: tuple[str, str]) -> None:
    session_id, device_id = seeded_device_session

    with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
        websocket.send_text(_hello_payload(session_id, device_id, local_last_seq=7))
        hello_ack = websocket.receive_json()

        assert hello_ack["type"] == "HELLO_ACK"
        assert hello_ack["device_id"] == device_id
        assert hello_ack["session_id"] == session_id
        assert hello_ack["local_last_seq"] == 7
        assert hello_ack["backend_last_seq"] == 0


def test_ws_device_handshake_reads_durable_last_seq(client: TestClient, seeded_device_session: tuple[str, str]) -> None:
    session_id, device_id = seeded_device_session

    settings = get_settings()
    sensor_dir = settings.data_root / "sessions" / session_id / "sensor"
    sensor_dir.mkdir(parents=True, exist_ok=True)
    state_path = sensor_dir / f"chest_{device_id}.state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "device_id": device_id,
                "device_role": "chest",
                "last_seq": 42,
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
        websocket.send_text(_hello_payload(session_id, device_id, local_last_seq=10))
        hello_ack = websocket.receive_json()
        assert hello_ack["type"] == "HELLO_ACK"
        assert hello_ack["backend_last_seq"] == 42


def test_ws_handshake_rejects_non_running_session(client: TestClient, session_factory: sessionmaker) -> None:
    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"
    with session_factory() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=False))
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
        websocket.send_text(_hello_payload(session_id, device_id))
        error = websocket.receive_json()
        assert error["type"] == "ERROR"
        assert error["code"] == "SESSION_NOT_RUNNING"


def test_ws_handshake_rejects_device_not_mapped(client: TestClient, session_factory: sessionmaker) -> None:
    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"
    with session_factory() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=False))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.commit()

    with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
        websocket.send_text(_hello_payload(session_id, device_id))
        error = websocket.receive_json()
        assert error["type"] == "ERROR"
        assert error["code"] == "DEVICE_NOT_IN_SESSION"


def test_ws_device_ack_and_duplicate_batch(client: TestClient, seeded_device_session: tuple[str, str]) -> None:
    session_id, device_id = seeded_device_session
    payload = _build_sensor_batch(session_id, device_id, start_seq=1, end_seq=2)

    with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
        websocket.send_text(_hello_payload(session_id, device_id))
        _ = websocket.receive_json()

        websocket.send_bytes(payload)
        ack_first = websocket.receive_json()
        assert ack_first["type"] == "ACK"
        assert ack_first["batch_start_seq"] == 1
        assert ack_first["batch_end_seq"] == 2
        assert ack_first["last_received_seq"] == 2
        assert ack_first["duplicate"] is False

        websocket.send_bytes(payload)
        ack_duplicate = websocket.receive_json()
        assert ack_duplicate["type"] == "ACK"
        assert ack_duplicate["last_received_seq"] == 2
        assert ack_duplicate["duplicate"] is True
        assert ack_duplicate["duplicate_batches"] >= 1


def test_ws_binary_batch_persists_csv_and_raw_binlog(client: TestClient, seeded_device_session: tuple[str, str]) -> None:
    session_id, device_id = seeded_device_session
    payload = _build_sensor_batch(session_id, device_id, start_seq=10, end_seq=12)

    with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
        websocket.send_text(_hello_payload(session_id, device_id))
        _ = websocket.receive_json()

        websocket.send_bytes(payload)
        ack = websocket.receive_json()
        assert ack["type"] == "ACK"
        assert ack["duplicate"] is False
        assert ack["last_received_seq"] == 12

    csv_writer_service.flush_session(session_id)
    csv_writer_service.close_session(session_id)

    settings = get_settings()
    sensor_dir = settings.data_root / "sessions" / session_id / "sensor"
    csv_path = sensor_dir / f"chest_{device_id}.csv"
    binlog_path = sensor_dir / f"chest_{device_id}.binlog"
    binlog_index_path = sensor_dir / f"chest_{device_id}.binlog.index.jsonl"

    assert csv_path.exists()
    csv_lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(csv_lines) >= 4  # header + 3 rows

    assert binlog_path.exists()
    assert binlog_path.stat().st_size > 0

    assert binlog_index_path.exists()
    index_lines = binlog_index_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(index_lines) >= 1


def test_ws_timeout_publishes_device_offline_event(client: TestClient, seeded_device_session: tuple[str, str]) -> None:
    session_id, device_id = seeded_device_session
    previous_timeout = ws_runtime._settings.ws_device_timeout_seconds
    ws_runtime._settings.ws_device_timeout_seconds = 1

    try:
        with client.websocket_connect(f"/ws/dashboard/{session_id}") as dashboard_ws:
            snapshot = dashboard_ws.receive_json()
            status_event = dashboard_ws.receive_json()
            assert snapshot["type"] == "DASHBOARD_SNAPSHOT"
            assert status_event["type"] == "VIDEO_RECORDER_STATUS"

            with client.websocket_connect(f"/ws/device/{device_id}") as device_ws:
                device_ws.send_text(_hello_payload(session_id, device_id))
                _ = device_ws.receive_json()

                online_event = dashboard_ws.receive_json()
                assert online_event["type"] == "DEVICE_ONLINE"
                assert online_event["device_id"] == device_id

                time.sleep(2.2)
                offline_event = dashboard_ws.receive_json()
                assert offline_event["type"] == "DEVICE_OFFLINE"
                assert offline_event["device_id"] == device_id
                assert offline_event["reason"] == "heartbeat_timeout"
    finally:
        ws_runtime._settings.ws_device_timeout_seconds = previous_timeout
