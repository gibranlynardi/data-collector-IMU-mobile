import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import FileArtifact


def ensure_session_layout(session_id: str) -> Path:
    settings = get_settings()
    session_root = settings.data_root / "sessions" / session_id
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
        ("sync_report", session_root / "sync_report.json"),
        ("preflight_report", session_root / "preflight_report.json"),
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
    _upsert_artifact_record(db, session_id, "export_zip", export_zip_path)
    db.commit()
    return manifest_path, export_zip_path
