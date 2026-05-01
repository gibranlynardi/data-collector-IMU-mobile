from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SESSION_FK = "sessions.session_id"


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    device_role: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    recording: Mapped[bool] = mapped_column(Boolean, default=False)
    battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_free_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_hz: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    jitter_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    preflight_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SessionDevice(Base):
    __tablename__ = "session_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey(SESSION_FK), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceSamplingTelemetry(Base):
    __tablename__ = "device_sampling_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey(SESSION_FK), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), index=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    recording: Mapped[bool] = mapped_column(Boolean, default=False)
    battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_free_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_hz: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    jitter_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Annotation(Base):
    __tablename__ = "annotations"

    annotation_id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey(SESSION_FK), index=True)
    label: Mapped[str] = mapped_column(String(128), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class AnnotationAudit(Base):
    __tablename__ = "annotation_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    annotation_id: Mapped[str] = mapped_column(ForeignKey("annotations.annotation_id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey(SESSION_FK), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    old_value_json: Mapped[str] = mapped_column(Text)
    new_value_json: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VideoRecording(Base):
    __tablename__ = "video_recordings"

    video_id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey(SESSION_FK), index=True)
    camera_id: Mapped[str] = mapped_column(String(64), default="webcam-0")
    file_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="PLANNED")
    video_start_server_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_start_monotonic_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_end_server_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_end_monotonic_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dropped_frame_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PreflightCheck(Base):
    __tablename__ = "preflight_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey(SESSION_FK), nullable=True, index=True)
    check_name: Mapped[str] = mapped_column(String(128), index=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FileArtifact(Base):
    __tablename__ = "file_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey(SESSION_FK), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    exists: Mapped[bool] = mapped_column(Boolean, default=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ArchiveUpload(Base):
    __tablename__ = "archive_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey(SESSION_FK), unique=True, index=True)
    uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperatorActionAudit(Base):
    __tablename__ = "operator_action_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operator_id: Mapped[str] = mapped_column(String(128), index=True)
    operator_type: Mapped[str] = mapped_column(String(32), default="operator")
    action: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey(SESSION_FK), nullable=True, index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
