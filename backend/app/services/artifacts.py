import hashlib
import json
import re
from csv import DictReader, DictWriter, writer
from datetime import UTC
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Annotation, Device, FileArtifact, PreflightCheck, Session as SessionModel, SessionDevice

SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"


def _validated_session_root(session_id: str) -> Path:
    if not re.fullmatch(SESSION_ID_PATTERN, session_id):
        raise ValueError("invalid session_id format")
    settings = get_settings()
    return settings.data_root / "sessions" / session_id


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = path.with_name(f"{path.name}.partial")
    partial_path.write_text(content, encoding="utf-8")
    partial_path.replace(path)


def _atomic_write_json(path: Path, payload: dict | list) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=True, indent=2))


def ensure_session_layout(session_id: str) -> Path:
    session_root = _validated_session_root(session_id)
    (session_root / "sensor").mkdir(parents=True, exist_ok=True)
    (session_root / "video").mkdir(parents=True, exist_ok=True)
    (session_root / "logs").mkdir(parents=True, exist_ok=True)
    (session_root / "export").mkdir(parents=True, exist_ok=True)
    return session_root


def seed_session_artifacts(db: Session, session_id: str, session_root: Path) -> None:
    defaults = [
        ("manifest", session_root / "manifest.json"),
        ("session", session_root / "session.json"),
        ("devices", session_root / "devices.json"),
        ("annotations", session_root / "annotations.csv"),
        ("completeness_report", session_root / "completeness_report.json"),
        ("sync_report", session_root / "sync_report.json"),
        ("preflight_report", session_root / "preflight_report.json"),
        ("backend_log", session_root / "logs" / "backend.log"),
        ("device_events_log", session_root / "logs" / "device_events.log"),
        ("warnings_log", session_root / "logs" / "warnings.log"),
        ("export_zip", session_root / "export" / f"{session_id}_dataset.zip"),
    ]

    for artifact_type, path in defaults:
        exists = path.exists()
        size_bytes = path.stat().st_size if exists else None
        db.add(
            FileArtifact(
                session_id=session_id,
                artifact_type=artifact_type,
                file_path=str(path),
                exists=exists,
                size_bytes=size_bytes,
            )
        )
    db.commit()


def materialize_session_storage(db: Session, session_id: str) -> None:
    session_root = ensure_session_layout(session_id)

    session = db.get(SessionModel, session_id)
    if session is None:
        raise ValueError("session not found")

    session_json_path = session_root / "session.json"
    session_payload = {
        "session_id": session.session_id,
        "status": session.status,
        "preflight_passed": bool(session.preflight_passed),
        "override_reason": session.override_reason,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
        "finalized_at": session.finalized_at.isoformat() if session.finalized_at else None,
    }
    _atomic_write_json(session_json_path, session_payload)

    rows = (
        db.query(SessionDevice, Device)
        .join(Device, SessionDevice.device_id == Device.device_id)
        .filter(SessionDevice.session_id == session_id)
        .order_by(SessionDevice.device_id.asc())
        .all()
    )
    devices_payload = {
        "session_id": session_id,
        "devices": [
            {
                "device_id": device.device_id,
                "device_role": (device.device_role or "other").lower(),
                "display_name": device.display_name,
                "required": bool(mapping.required),
                "connected": bool(device.connected),
            }
            for mapping, device in rows
        ],
    }
    _atomic_write_json(session_root / "devices.json", devices_payload)

    annotations = (
        db.query(Annotation)
        .filter(Annotation.session_id == session_id)
        .order_by(Annotation.started_at.asc(), Annotation.annotation_id.asc())
        .all()
    )
    annotations_path = session_root / "annotations.csv"
    partial_annotations_path = annotations_path.with_name(f"{annotations_path.name}.partial")
    partial_annotations_path.parent.mkdir(parents=True, exist_ok=True)
    with partial_annotations_path.open("w", encoding="utf-8", newline="") as file_obj:
        csv_writer = writer(file_obj)
        csv_writer.writerow([
            "annotation_id",
            "session_id",
            "label",
            "notes",
            "started_at",
            "ended_at",
            "auto_closed",
            "deleted",
        ])
        for item in annotations:
            csv_writer.writerow(
                [
                    item.annotation_id,
                    item.session_id,
                    item.label,
                    item.notes or "",
                    item.started_at.isoformat() if item.started_at else "",
                    item.ended_at.isoformat() if item.ended_at else "",
                    bool(item.auto_closed),
                    bool(item.deleted),
                ]
            )
    partial_annotations_path.replace(annotations_path)

    checks = (
        db.query(PreflightCheck)
        .filter(PreflightCheck.session_id == session_id)
        .order_by(PreflightCheck.measured_at.asc(), PreflightCheck.id.asc())
        .all()
    )
    preflight_payload = {
        "session_id": session_id,
        "checks": [
            {
                "check_name": item.check_name,
                "passed": bool(item.passed),
                "details": item.details,
                "measured_at": item.measured_at.isoformat() if item.measured_at else None,
            }
            for item in checks
        ],
    }
    _atomic_write_json(session_root / "preflight_report.json", preflight_payload)

    # Ensure mandatory log placeholders exist in session logs directory.
    for log_file in [
        session_root / "logs" / "backend.log",
        session_root / "logs" / "device_events.log",
        session_root / "logs" / "warnings.log",
    ]:
        if not log_file.exists():
            _atomic_write_text(log_file, "")

    _upsert_artifact_record(db, session_id, "session", session_json_path)
    _upsert_artifact_record(db, session_id, "devices", session_root / "devices.json")
    _upsert_artifact_record(db, session_id, "annotations", annotations_path)
    _upsert_artifact_record(db, session_id, "completeness_report", session_root / "completeness_report.json")
    _upsert_artifact_record(db, session_id, "preflight_report", session_root / "preflight_report.json")
    _upsert_artifact_record(db, session_id, "backend_log", session_root / "logs" / "backend.log")
    _upsert_artifact_record(db, session_id, "device_events_log", session_root / "logs" / "device_events.log")
    _upsert_artifact_record(db, session_id, "warnings_log", session_root / "logs" / "warnings.log")
    db.commit()


def _to_unix_ns(value) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return int(value.replace(tzinfo=UTC).timestamp() * 1_000_000_000)
    return int(value.timestamp() * 1_000_000_000)


def _build_annotation_intervals(db: Session, session_id: str) -> list[dict[str, object]]:
    rows = (
        db.query(Annotation)
        .filter(Annotation.session_id == session_id, Annotation.deleted.is_(False))
        .order_by(Annotation.started_at.asc(), Annotation.annotation_id.asc())
        .all()
    )
    intervals: list[dict[str, object]] = []
    for item in rows:
        start_ns = _to_unix_ns(item.started_at)
        end_ns = _to_unix_ns(item.ended_at)
        if start_ns is None:
            continue
        intervals.append(
            {
                "annotation_id": item.annotation_id,
                "label": item.label,
                "start_ns": start_ns,
                "end_ns": end_ns,
            }
        )
    return intervals


def _pick_annotation(ts_ns: int, intervals: list[dict[str, object]]) -> tuple[str, str]:
    for item in intervals:
        start_ns = int(item["start_ns"])
        end_ns = int(item["end_ns"]) if item.get("end_ns") is not None else None
        if ts_ns < start_ns:
            continue
        if end_ns is not None and ts_ns > end_ns:
            continue
        return str(item["annotation_id"]), str(item["label"])
    return "", ""


def build_labeled_dataset_exports(db: Session, session_id: str, session_root: Path) -> tuple[list[Path], Path]:
    sensor_dir = session_root / "sensor"
    export_labeled_dir = session_root / "export" / "labeled"
    export_labeled_dir.mkdir(parents=True, exist_ok=True)

    intervals = _build_annotation_intervals(db, session_id)
    sensor_csv_files = sorted(path for path in sensor_dir.glob("*.csv") if path.is_file())

    per_device_paths: list[Path] = []
    all_rows: list[dict[str, str]] = []
    all_fieldnames: list[str] = []

    for csv_path in sensor_csv_files:
        with csv_path.open("r", encoding="utf-8", newline="") as src:
            reader = DictReader(src)
            fieldnames = list(reader.fieldnames or [])
            if "annotation_id" not in fieldnames:
                fieldnames.append("annotation_id")
            if "annotation_label" not in fieldnames:
                fieldnames.append("annotation_label")
            if not all_fieldnames:
                all_fieldnames = list(fieldnames)

            labeled_path = export_labeled_dir / f"{csv_path.stem}_labeled.csv"
            with labeled_path.open("w", encoding="utf-8", newline="") as dst:
                writer_obj = DictWriter(dst, fieldnames=fieldnames)
                writer_obj.writeheader()
                for row in reader:
                    ts_raw = row.get("timestamp_server_unix_ns") or row.get("estimated_server_unix_ns") or row.get("timestamp_device_unix_ns")
                    try:
                        ts_ns = int(ts_raw or 0)
                    except Exception:
                        ts_ns = 0
                    annotation_id, label = _pick_annotation(ts_ns, intervals)
                    row["annotation_id"] = annotation_id
                    row["annotation_label"] = label
                    writer_obj.writerow(row)
                    all_rows.append({name: str(row.get(name, "")) for name in fieldnames})

            per_device_paths.append(labeled_path)

    combined_path = export_labeled_dir / "all_devices_labeled.csv"
    combined_fieldnames = all_fieldnames or ["annotation_id", "annotation_label"]
    with combined_path.open("w", encoding="utf-8", newline="") as dst:
        writer_obj = DictWriter(dst, fieldnames=combined_fieldnames)
        writer_obj.writeheader()
        for row in all_rows:
            writer_obj.writerow({name: row.get(name, "") for name in combined_fieldnames})

    return per_device_paths, combined_path


def _checksum_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _upsert_artifact_record(db: Session, session_id: str, artifact_type: str, path: Path) -> None:
    artifact = (
        db.query(FileArtifact)
        .filter(FileArtifact.session_id == session_id, FileArtifact.artifact_type == artifact_type)
        .first()
    )
    exists = path.exists()
    size_bytes = path.stat().st_size if exists else None
    checksum = _checksum_sha256(path) if exists else None

    if artifact:
        artifact.file_path = str(path)
        artifact.exists = exists
        artifact.size_bytes = size_bytes
        artifact.checksum = checksum
        return

    db.add(
        FileArtifact(
            session_id=session_id,
            artifact_type=artifact_type,
            file_path=str(path),
            exists=exists,
            size_bytes=size_bytes,
            checksum=checksum,
        )
    )


def finalize_session_artifacts(db: Session, session_id: str) -> tuple[Path, Path]:
    settings = get_settings()
    session_root = ensure_session_layout(session_id)
    materialize_session_storage(db, session_id)
    per_device_labeled, combined_labeled = build_labeled_dataset_exports(db, session_id, session_root)

    manifest_path = session_root / "manifest.json"
    export_dir = session_root / "export"
    export_zip_path = export_dir / f"{session_id}_dataset.zip"

    files = []
    for file_path in sorted(session_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path == export_zip_path:
            continue
        rel_path = file_path.relative_to(settings.data_root).as_posix()
        files.append(
            {
                "relative_path": rel_path,
                "size_bytes": file_path.stat().st_size,
                "sha256": _checksum_sha256(file_path),
            }
        )

    manifest_payload = {
        "session_id": session_id,
        "schema_version": "1.0.0",
        "file_count": len(files),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=True, indent=2), encoding="utf-8")

    with ZipFile(export_zip_path, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for file_path in sorted(session_root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path == export_zip_path:
                continue
            zip_file.write(file_path, arcname=file_path.relative_to(session_root).as_posix())

    _upsert_artifact_record(db, session_id, "manifest", manifest_path)
    _upsert_artifact_record(db, session_id, "sync_report", session_root / "sync_report.json")
    _upsert_artifact_record(db, session_id, "labeled_dataset_combined", combined_labeled)
    for index, file_path in enumerate(per_device_labeled, start=1):
        _upsert_artifact_record(db, session_id, f"labeled_dataset_device_{index}", file_path)
    _upsert_artifact_record(db, session_id, "export_zip", export_zip_path)
    db.commit()
    return manifest_path, export_zip_path
