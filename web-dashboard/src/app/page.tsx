"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  anonymizeVideo,
  assignSessionDevices,
  createSession,
  deleteAnnotation,
  fetchArchiveUploadStatus,
  fetchAnnotations,
  fetchArtifacts,
  fetchDevices,
  fetchHealth,
  fetchPreflight,
  fetchSessionSamplingQualityHistory,
  fetchSessionCompleteness,
  fetchSession,
  fetchSessionDevices,
  fetchSyncReport,
  fetchUploadInstructions,
  fetchVideoMetadata,
  fetchVideoStatus,
  finalizeSession,
  finalizeSessionWithReason,
  getApiBaseUrl,
  markArchiveUploaded,
  patchAnnotation,
  startAnnotation,
  startSession,
  stopAnnotation,
  stopSession,
  webcamSnapshotUrl,
} from "@/lib/api";
import type {
  AnnotationResponse,
  ArchiveUploadStatusResponse,
  ArtifactResponse,
  DashboardEvent,
  DeviceResponse,
  HealthResponse,
  PreflightResponse,
  SessionCompletenessResponse,
  SessionBinding,
  SessionDeviceAssignItem,
  SamplingQualityPoint,
  SessionResponse,
  SyncReport,
  UploadInstructionsResponse,
  VideoAnonymizeResponse,
  VideoMetadataResponse,
  VideoStatusResponse,
} from "@/lib/types";

type PreviewPoint = {
  x: number;
  accX: number;
  accY: number;
  accZ: number;
  gyroX: number;
  gyroY: number;
  gyroZ: number;
};

type DevicePreviewStore = Record<string, PreviewPoint[]>;
type DeviceSamplingHistoryStore = Record<string, SamplingQualityPoint[]>;

const API_BASE = getApiBaseUrl();
const WS_BASE_OVERRIDE = process.env.NEXT_PUBLIC_WS_BASE_URL;
const OPERATOR_WS_TOKEN = process.env.NEXT_PUBLIC_OPERATOR_API_TOKEN ?? "";
const OPERATOR_WS_ID = process.env.NEXT_PUBLIC_OPERATOR_ID ?? "dashboard-web";
const PREVIEW_WINDOW_MS = 30_000;
const SAMPLING_HISTORY_LIMIT = 96;
const SAMPLING_TARGET_INTERVAL_MS = 10;

function buildWsBase(apiBase: string, wsPort: number | null): string {
  if (WS_BASE_OVERRIDE && WS_BASE_OVERRIDE.trim()) {
    return WS_BASE_OVERRIDE.trim();
  }
  const url = new URL(apiBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (wsPort && wsPort > 0) {
    url.port = String(wsPort);
  }
  return url.origin;
}

function statusBadge(status: "idle" | "pending" | "running" | "completed" | "failed"): string {
  if (status === "completed") {
    return "bg-[#d4f3df] text-[#245f3b]";
  }
  if (status === "failed") {
    return "bg-[#f7d6cc] text-[#8b3727]";
  }
  if (status === "running" || status === "pending") {
    return "bg-[#ffe3ce] text-[#824622]";
  }
  return "bg-[#e9e0d2] text-[#5e4f3d]";
}

function isJsonArray(value: unknown): value is Array<Record<string, unknown>> {
  return Array.isArray(value);
}

function mergeDeviceSnapshot(devices: DeviceResponse[], snapshot: Array<Record<string, unknown>>): DeviceResponse[] {
  return devices.map((item) => {
    const hit = snapshot.find((candidate) => candidate.device_id === item.device_id);
    return hit ? { ...item, connected: Boolean(hit.online) } : item;
  });
}

function annotationStatusText(annotation: AnnotationResponse): string {
  if (!annotation.ended_at) {
    return "active";
  }
  return annotation.auto_closed ? "auto-closed" : "closed";
}

function bytesToHuman(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function secondsToClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hh = String(Math.floor(total / 3600)).padStart(2, "0");
  const mm = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function parseIsoTimestamp(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function annotationDurationText(annotation: AnnotationResponse): string {
  const startMs = parseIsoTimestamp(annotation.started_at);
  if (!startMs) {
    return "-";
  }
  const endMs = annotation.ended_at ? parseIsoTimestamp(annotation.ended_at) : Date.now();
  if (!endMs || endMs < startMs) {
    return "-";
  }
  return secondsToClock((endMs - startMs) / 1000);
}
const MIN_BATTERY_PERCENT = 20;
const MIN_STORAGE_FREE_MB = 512;

function sparkline(points: number[], width = 280, height = 84): string {
  if (points.length === 0) {
    return "";
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = Math.max(1e-6, max - min);
  return points
    .map((point, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - ((point - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function buildSamplingHistoryStore(points: SamplingQualityPoint[]): DeviceSamplingHistoryStore {
  const bucket: DeviceSamplingHistoryStore = {};
  for (const point of points) {
    const key = point.device_id;
    if (!bucket[key]) {
      bucket[key] = [];
    }
    bucket[key].push(point);
  }
  for (const key of Object.keys(bucket)) {
    bucket[key].sort((a, b) => Date.parse(a.measured_at) - Date.parse(b.measured_at));
    if (bucket[key].length > SAMPLING_HISTORY_LIMIT) {
      bucket[key] = bucket[key].slice(-SAMPLING_HISTORY_LIMIT);
    }
  }
  return bucket;
}

function appendSamplingHistoryPoint(
  store: DeviceSamplingHistoryStore,
  point: SamplingQualityPoint,
): DeviceSamplingHistoryStore {
  const current = store[point.device_id] ?? [];
  const next = [...current, point].sort((a, b) => Date.parse(a.measured_at) - Date.parse(b.measured_at));
  const trimmed = next.length > SAMPLING_HISTORY_LIMIT ? next.slice(-SAMPLING_HISTORY_LIMIT) : next;
  return { ...store, [point.device_id]: trimmed };
}

function jitterQualityTone(jitterP99Ms: number | null): { label: string; className: string } {
  if (jitterP99Ms === null || !Number.isFinite(jitterP99Ms)) {
    return { label: "unknown", className: "bg-[#ebe3d6] text-[#5e4f3d]" };
  }
  if (jitterP99Ms <= 3) {
    return { label: "stable", className: "bg-[#d4f3df] text-[#245f3b]" };
  }
  if (jitterP99Ms <= 6) {
    return { label: "degrading", className: "bg-[#ffe3ce] text-[#824622]" };
  }
  return { label: "critical", className: "bg-[#f7d6cc] text-[#8b3727]" };
}

export default function Home() {
  const [sessionIdInput, setSessionIdInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [newLabel, setNewLabel] = useState("adl.walk.normal");
  const [newNote, setNewNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string>("Dashboard ready");

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [preflight, setPreflight] = useState<PreflightResponse | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [devices, setDevices] = useState<DeviceResponse[]>([]);
  const [bindings, setBindings] = useState<SessionBinding[]>([]);
  const [requiredRoles, setRequiredRoles] = useState<string[]>([]);
  const [annotations, setAnnotations] = useState<AnnotationResponse[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactResponse[]>([]);
  const [syncReport, setSyncReport] = useState<SyncReport | null>(null);
  const [video, setVideo] = useState<VideoStatusResponse | null>(null);
  const [videoMetadata, setVideoMetadata] = useState<VideoMetadataResponse | null>(null);
  const [anonymizeMode, setAnonymizeMode] = useState<boolean>(false);
  const [anonymizeState, setAnonymizeState] = useState<"idle" | "pending" | "running" | "completed" | "failed">("idle");
  const [anonymizeResult, setAnonymizeResult] = useState<VideoAnonymizeResponse | null>(null);
  const [clockNow, setClockNow] = useState<number>(() => Date.now());
  const [uploadInstructions, setUploadInstructions] = useState<UploadInstructionsResponse | null>(null);
  const [archiveUpload, setArchiveUpload] = useState<ArchiveUploadStatusResponse | null>(null);
  const [uploadedBy, setUploadedBy] = useState("operator");
  const [remotePathInput, setRemotePathInput] = useState("");
  const [completeness, setCompleteness] = useState<SessionCompletenessResponse | null>(null);
  const [showFinalizeIncompleteModal, setShowFinalizeIncompleteModal] = useState(false);
  const [finalizeIncompleteReason, setFinalizeIncompleteReason] = useState("");
  const [webcamFrameTick, setWebcamFrameTick] = useState(0);

  const [startBarrierUnixNs, setStartBarrierUnixNs] = useState<number | null>(null);
  const [countdownMs, setCountdownMs] = useState<number>(0);
  const [previewByDevice, setPreviewByDevice] = useState<DevicePreviewStore>({});
  const [samplingHistoryByDevice, setSamplingHistoryByDevice] = useState<DeviceSamplingHistoryStore>({});

  const selectedSession = sessionId.trim();
  const activeAnnotations = annotations.filter((item) => !item.ended_at && !item.deleted);
  const wsBase = useMemo(() => buildWsBase(API_BASE, health?.ws_port ?? null), [health?.ws_port]);
  const webcamSnapshot = useMemo(() => `${webcamSnapshotUrl()}?t=${webcamFrameTick}`, [webcamFrameTick]);

  const elapsedSeconds = useMemo(() => {
    if (!session?.started_at) {
      return 0;
    }
    const start = Date.parse(session.started_at);
    const end = session.stopped_at ? Date.parse(session.stopped_at) : clockNow;
    return Math.max(0, (end - start) / 1000);
  }, [clockNow, session]);

  const videoElapsedSeconds = useMemo(() => {
    if (!video) {
      return 0;
    }
    if (video.elapsed_ms > 0) {
      return Math.floor(video.elapsed_ms / 1000);
    }
    if (videoMetadata?.duration_ms) {
      return Math.floor(videoMetadata.duration_ms / 1000);
    }
    return 0;
  }, [video, videoMetadata]);

  const famsReady = useMemo(() => {
    const hasManifest = artifacts.some((item) => item.artifact_type === "manifest" && item.exists);
    const hasExport = artifacts.some((item) => item.artifact_type === "export_zip" && item.exists);
    const hasVideo =
      artifacts.some((item) => item.artifact_type === "video" && item.exists) ||
      artifacts.some((item) => item.exists && item.file_path.toLowerCase().includes("/video/")) ||
      artifacts.some((item) => item.exists && item.file_path.toLowerCase().includes("\\video\\")) ||
      Boolean(videoMetadata?.file_path);
    return hasManifest && hasExport && hasVideo;
  }, [artifacts, videoMetadata?.file_path]);

  const requiredBindings = useMemo(() => bindings.filter((item) => item.required), [bindings]);
  const requiredOnlineCount = useMemo(() => requiredBindings.filter((item) => item.connected).length, [requiredBindings]);
  const requiredOnlineOk = useMemo(
    () => requiredBindings.length > 0 && requiredOnlineCount === requiredBindings.length,
    [requiredBindings.length, requiredOnlineCount],
  );

  const allDevicesWithHz = useMemo(
    () => devices.length > 0 && devices.every((item) => item.effective_hz !== null),
    [devices],
  );
  const expectedHzOk = useMemo(
    () => allDevicesWithHz && devices.every((item) => Number(item.effective_hz) >= 95),
    [allDevicesWithHz, devices],
  );

  const requiredRoleCoverageOk = useMemo(() => {
    if (requiredRoles.length === 0) {
      return false;
    }
    const assignedRoles = new Set(requiredBindings.map((item) => item.device_role.toLowerCase()));
    return requiredRoles.every((role) => assignedRoles.has(role.toLowerCase()));
  }, [requiredBindings, requiredRoles]);

  const requiredDevices = useMemo(
    () => requiredBindings.map((binding) => devices.find((device) => device.device_id === binding.device_id)).filter((item): item is DeviceResponse => Boolean(item)),
    [devices, requiredBindings],
  );

  const batteryOk = useMemo(
    () => requiredDevices.length > 0 && requiredDevices.every((item) => item.battery_percent !== null && item.battery_percent >= MIN_BATTERY_PERCENT),
    [requiredDevices],
  );

  const storageOk = useMemo(
    () => requiredDevices.length > 0 && requiredDevices.every((item) => item.storage_free_mb !== null && item.storage_free_mb >= MIN_STORAGE_FREE_MB),
    [requiredDevices],
  );

  const runAction = useCallback(async (title: string, action: () => Promise<void>) => {
    try {
      setError(null);
      await action();
      setInfo(title);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }, []);

  const reloadSessionData = useCallback(async () => {
    if (!selectedSession) {
      return;
    }

    const [sessionPayload, bindingPayload, annotationPayload, artifactPayload, syncPayload, videoPayload] = await Promise.all([
      fetchSession(selectedSession),
      fetchSessionDevices(selectedSession),
      fetchAnnotations(selectedSession),
      fetchArtifacts(selectedSession),
      fetchSyncReport(selectedSession),
      fetchVideoStatus(selectedSession),
    ]);

    setSession(sessionPayload);
    setBindings(bindingPayload.bindings);
    setRequiredRoles(bindingPayload.required_roles);
    setAnnotations(annotationPayload);
    setArtifacts(artifactPayload);
    setSyncReport(syncPayload);
    setVideo(videoPayload);

    const [uploadInstructionsPayload, archiveUploadPayload, completenessPayload, samplingQualityPayload] = await Promise.all([
      fetchUploadInstructions(selectedSession).catch(() => null),
      fetchArchiveUploadStatus(selectedSession).catch(() => null),
      fetchSessionCompleteness(selectedSession).catch(() => null),
      fetchSessionSamplingQualityHistory(selectedSession, { limit: SAMPLING_HISTORY_LIMIT }).catch(() => null),
    ]);
    setUploadInstructions(uploadInstructionsPayload);
    setArchiveUpload(archiveUploadPayload);
    if (archiveUploadPayload?.remote_path) {
      setRemotePathInput(archiveUploadPayload.remote_path);
    } else if (uploadInstructionsPayload?.remote_target) {
      setRemotePathInput(uploadInstructionsPayload.remote_target);
    }
    setCompleteness(completenessPayload);
    setSamplingHistoryByDevice(buildSamplingHistoryStore(samplingQualityPayload?.points ?? []));

    try {
      const metadataPayload = await fetchVideoMetadata(selectedSession);
      setVideoMetadata(metadataPayload);
    } catch {
      setVideoMetadata(null);
    }

    if (syncPayload.server_start_time_unix_ns) {
      setStartBarrierUnixNs(syncPayload.server_start_time_unix_ns);
    }
  }, [selectedSession]);

  const autoAssignRequiredRoles = useCallback(async () => {
    if (!selectedSession) {
      throw new Error("Connect session terlebih dahulu");
    }
    if (requiredRoles.length === 0) {
      throw new Error("required roles tidak tersedia");
    }

    const roleAssignments: SessionDeviceAssignItem[] = [];
    const lowerRequired = requiredRoles.map((item) => item.toLowerCase());
    for (const role of lowerRequired) {
      const matched = devices.find((item) => item.device_role.toLowerCase() === role);
      if (!matched) {
        throw new Error(`Tidak ada device untuk role ${role}`);
      }
      roleAssignments.push({ device_id: matched.device_id, required: true });
    }

    const used = new Set(roleAssignments.map((item) => item.device_id));
    const optionalAssignments = devices
      .filter((item) => !used.has(item.device_id))
      .map((item) => ({ device_id: item.device_id, required: false }));

    await assignSessionDevices(selectedSession, [...roleAssignments, ...optionalAssignments], true);
    await reloadSessionData();
  }, [devices, reloadSessionData, requiredRoles, selectedSession]);

  const runAnonymize = useCallback(async (targetSession: string) => {
    setAnonymizeState("pending");
    setAnonymizeResult(null);
    setAnonymizeState("running");
    const result = await anonymizeVideo(targetSession);
    setAnonymizeResult(result);
    setAnonymizeState(result.status === "completed" ? "completed" : "failed");
  }, []);

  const reloadBaseData = useCallback(async () => {
    const [healthPayload, preflightPayload, devicePayload] = await Promise.all([
      fetchHealth(),
      fetchPreflight(),
      fetchDevices(),
    ]);
    setHealth(healthPayload);
    setPreflight(preflightPayload);
    setDevices(devicePayload);
  }, []);

  useEffect(() => {
    let alive = true;
    const boot = async () => {
      try {
        await reloadBaseData();
        if (selectedSession) {
          await reloadSessionData();
        }
      } catch (err) {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    };
    void boot();
    return () => {
      alive = false;
    };
  }, [reloadBaseData, reloadSessionData, selectedSession]);

  useEffect(() => {
    const interval = globalThis.setInterval(() => {
      void reloadBaseData();
      if (selectedSession) {
        void reloadSessionData();
      }
    }, 5000);
    return () => globalThis.clearInterval(interval);
  }, [reloadBaseData, reloadSessionData, selectedSession]);

  useEffect(() => {
    const timer = globalThis.setInterval(() => setClockNow(Date.now()), 1000);
    return () => globalThis.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = globalThis.setInterval(() => {
      setWebcamFrameTick((prev) => prev + 1);
    }, 2000);
    return () => globalThis.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedSession) {
      return;
    }

    const wsQuery = new URLSearchParams();
    if (OPERATOR_WS_TOKEN) {
      wsQuery.set("operator_token", OPERATOR_WS_TOKEN);
    }
    if (OPERATOR_WS_ID) {
      wsQuery.set("operator_id", OPERATOR_WS_ID);
    }
    const wsSuffix = wsQuery.toString() ? `?${wsQuery.toString()}` : "";
    const ws = new WebSocket(`${wsBase}/ws/dashboard/${selectedSession}${wsSuffix}`);
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as DashboardEvent;
      if (payload.type === "SESSION_STATE") {
        setSession((prev) => (prev ? { ...prev, status: String(payload.status ?? prev.status) } : prev));
      }
      if (payload.type === "DASHBOARD_SNAPSHOT" && isJsonArray(payload.devices)) {
        const snapshot = payload.devices;
        setDevices((prev) => mergeDeviceSnapshot(prev, snapshot));
      }
      if (payload.type === "SENSOR_PREVIEW") {
        const deviceId = String(payload.device_id ?? "unknown");
        const lastSample = (payload.preview as { last_sample?: Record<string, unknown> } | undefined)?.last_sample;
        const accX = Number(lastSample?.acc_x_g ?? 0);
        const accY = Number(lastSample?.acc_y_g ?? 0);
        const accZ = Number(lastSample?.acc_z_g ?? 0);
        const gyroX = Number(lastSample?.gyro_x_deg ?? 0);
        const gyroY = Number(lastSample?.gyro_y_deg ?? 0);
        const gyroZ = Number(lastSample?.gyro_z_deg ?? 0);
        setPreviewByDevice((prev) => {
          const current = prev[deviceId] ?? [];
          const now = Date.now();
          const next = [...current, { x: now, accX, accY, accZ, gyroX, gyroY, gyroZ }].filter((item) => now - item.x <= PREVIEW_WINDOW_MS);
          return { ...prev, [deviceId]: next };
        });
      }
      if (payload.type === "CLOCK_SYNC_STATUS") {
        setSyncReport((prev) =>
          prev
            ? {
                ...prev,
                overall_sync_quality: String(payload.overall_sync_quality ?? prev.overall_sync_quality),
                overall_sync_quality_color: String(payload.overall_sync_quality_color ?? prev.overall_sync_quality_color),
                devices: Array.isArray(payload.devices) ? (payload.devices as SyncReport["devices"]) : prev.devices,
              }
            : prev,
        );
      }
      if (payload.type === "VIDEO_RECORDER_STATUS") {
        setVideo((prev) => (prev ? { ...prev, status: String(payload.status ?? prev.status) } : prev));
      }
      if (payload.type === "SESSION_STOP_SYNCING") {
        setInfo(`SYNCING: pending ${(payload.pending_devices as string[] | undefined)?.join(", ") ?? "-"}`);
      }
      if (payload.type === "INGEST_WARNING") {
        setInfo(`Warning ${String(payload.device_id ?? "device")}: ${String(payload.warning ?? "")}`);
      }
      if (payload.type === "ANNOTATION_EVENT") {
        void reloadSessionData();
      }
      if (payload.type === "SESSION_COMPLETENESS") {
        setCompleteness({
          session_id: selectedSession,
          complete: Boolean(payload.complete),
          checks: (payload.checks as Record<string, boolean>) ?? {},
          detail: (payload.detail as Record<string, unknown>) ?? {},
        });
      }
      if (payload.type === "DEVICE_SAMPLING_QUALITY") {
        const measuredAt = String(payload.measured_at ?? "").trim();
        const deviceId = String(payload.device_id ?? "").trim();
        if (!deviceId || !measuredAt) {
          return;
        }
        const point: SamplingQualityPoint = {
          device_id: deviceId,
          connected: Boolean(payload.connected ?? true),
          recording: Boolean(payload.recording ?? false),
          battery_percent: typeof payload.battery_percent === "number" ? payload.battery_percent : null,
          storage_free_mb: typeof payload.storage_free_mb === "number" ? payload.storage_free_mb : null,
          effective_hz: typeof payload.effective_hz === "number" ? payload.effective_hz : null,
          interval_p99_ms: typeof payload.interval_p99_ms === "number" ? payload.interval_p99_ms : null,
          jitter_p99_ms: typeof payload.jitter_p99_ms === "number" ? payload.jitter_p99_ms : null,
          measured_at: measuredAt,
        };
        setSamplingHistoryByDevice((prev) => appendSamplingHistoryPoint(prev, point));
      }
      const barrier = payload.server_start_time_unix_ns;
      if (typeof barrier === "number" && barrier > 0) {
        setStartBarrierUnixNs(barrier);
      }
    };

    ws.onerror = () => {
      setInfo("WS disconnected, fallback to polling");
    };

    return () => {
      ws.close();
    };
  }, [reloadSessionData, selectedSession, wsBase]);

  useEffect(() => {
    const timer = globalThis.setInterval(() => {
      if (!startBarrierUnixNs) {
        setCountdownMs(0);
        return;
      }
      const delta = Math.max(0, Math.floor((startBarrierUnixNs - Date.now() * 1_000_000) / 1_000_000));
      setCountdownMs(delta);
    }, 200);
    return () => globalThis.clearInterval(timer);
  }, [startBarrierUnixNs]);

  const completenessEntries = Object.entries(completeness?.checks ?? {});

  return (
    <div className="min-h-screen bg-[radial-gradient(80%_110%_at_10%_5%,#f4e8ce_0%,#f8f3e6_42%,#efe7d8_100%)] text-[#1e1b16]">
      <main className="mx-auto grid w-full max-w-[1500px] gap-4 px-4 py-4 md:px-6 md:py-6 xl:grid-cols-[1.2fr_1fr]">
        <section className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-[0_20px_60px_-35px_rgba(42,31,19,0.45)] backdrop-blur">
          <p className="font-display text-xs uppercase tracking-[0.4em] text-[#7a6650]">IMU Collector / Phase 7</p>
          <h1 className="mt-2 text-4xl font-semibold leading-tight md:text-5xl">Live Session Command Deck</h1>
          <p className="mt-3 max-w-2xl text-sm text-[#4e4234]">
            Dashboard operasional untuk create-start-stop-finalize, preflight, annotation timeline, sensor preview, sinkronisasi clock, dan
            artifact tracking.
          </p>

          <div className="mt-5 grid gap-3 md:grid-cols-5">
            <input
              value={sessionIdInput}
              onChange={(event) => setSessionIdInput(event.target.value)}
              placeholder="20260419_143022_A1B2C3D4"
              className="col-span-3 rounded-xl border border-black/20 bg-[#fffdfa] px-3 py-2 text-sm"
            />
            <button
              onClick={() => {
                setSessionId(sessionIdInput.trim());
                setSamplingHistoryByDevice({});
              }}
              className="rounded-xl bg-[#26221b] px-3 py-2 text-sm font-medium text-white"
            >
              Connect Session
            </button>
            <button
              onClick={() => {
                setSessionId("");
                setSessionIdInput("");
                setSamplingHistoryByDevice({});
              }}
              className="rounded-xl border border-black/20 bg-white px-3 py-2 text-sm"
            >
              Clear
            </button>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <InfoPill title="Session" value={selectedSession || "none"} />
            <InfoPill title="Status" value={session?.status ?? "idle"} />
            <InfoPill title="Elapsed" value={secondsToClock(elapsedSeconds)} />
            <InfoPill title="Start Barrier" value={countdownMs > 0 ? `${(countdownMs / 1000).toFixed(1)}s` : "ready"} />
          </div>
          <p className="mt-2 text-xs text-[#6a5a48]">REST {health?.rest_port ?? "-"} / WS {health?.ws_port ?? "-"}</p>

          {error ? <p className="mt-3 rounded-lg bg-[#fbdfd6] px-3 py-2 text-sm text-[#8f2f1d]">{error}</p> : null}
          <p className="mt-2 text-xs text-[#6a5a48]">{info}</p>
        </section>

        <section className="rounded-2xl border border-black/10 bg-[#17120c] p-5 text-[#f4ecdf] shadow-[0_20px_60px_-35px_rgba(0,0,0,0.7)]">
          <h2 className="font-display text-sm uppercase tracking-[0.25em] text-[#d4b782]">Session Controls</h2>
          <div className="mt-4 grid gap-2">
            <input
              value={overrideReason}
              onChange={(event) => setOverrideReason(event.target.value)}
              placeholder="override reason (optional)"
              className="rounded-xl border border-[#6c5537] bg-[#201911] px-3 py-2 text-sm"
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() =>
                  void runAction("Session created", async () => {
                    const created = await createSession({ session_id: sessionIdInput || undefined, override_reason: overrideReason || null });
                    setSessionId(created.session_id);
                    setSessionIdInput(created.session_id);
                    await reloadSessionData();
                  })
                }
                className="rounded-xl bg-[#d46f4a] px-3 py-2 text-sm font-medium text-white"
              >
                Create
              </button>
              <button
                onClick={() => selectedSession && void runAction("Session devices assigned", autoAssignRequiredRoles)}
                className="rounded-xl border border-[#6c5537] px-3 py-2 text-sm font-medium text-[#f4ecdf]"
              >
                Assign Required
              </button>
              <button
                onClick={() => selectedSession && void runAction("Session started", async () => {
                  await startSession(selectedSession);
                  await reloadSessionData();
                })}
                className="rounded-xl bg-[#3f8d66] px-3 py-2 text-sm font-medium text-white"
              >
                Start
              </button>
              <button
                onClick={() => selectedSession && void runAction("Stop requested", async () => {
                  if (anonymizeMode) {
                    const confirmed = globalThis.confirm("Toggle anonymize aktif. Jalankan anonymize setelah STOP?");
                    if (!confirmed) {
                      return;
                    }
                  }
                  await stopSession(selectedSession);
                  if (anonymizeMode) {
                    await runAnonymize(selectedSession);
                  }
                  await reloadSessionData();
                })}
                className="rounded-xl bg-[#a24f3c] px-3 py-2 text-sm font-medium text-white"
              >
                Stop
              </button>
              <button
                onClick={() => selectedSession && void runAction("Session finalized", async () => {
                  if (anonymizeMode) {
                    const confirmed = globalThis.confirm("Toggle anonymize aktif. Jalankan anonymize setelah FINALIZE?");
                    if (!confirmed) {
                      return;
                    }
                  }
                  await finalizeSession(selectedSession, false);
                  if (anonymizeMode) {
                    await runAnonymize(selectedSession);
                  }
                  await reloadSessionData();
                })}
                className="rounded-xl bg-[#8a7540] px-3 py-2 text-sm font-medium text-white"
              >
                Finalize
              </button>
              <button
                onClick={() => selectedSession && void runAction("Completeness checked", async () => {
                  const report = await fetchSessionCompleteness(selectedSession);
                  setCompleteness(report);
                  setShowFinalizeIncompleteModal(true);
                })}
                className="rounded-xl border border-[#d4b782] bg-[#2a2117] px-3 py-2 text-sm font-medium text-[#f4ecdf]"
              >
                Finalize Incomplete
              </button>
            </div>
          </div>
        </section>

        <section className="grid gap-4 xl:col-span-2 xl:grid-cols-3">
          <Panel title="Preflight Checklist" subtitle="Backend + storage + webcam + required device readiness">
            <ChecklistRow label="Backend healthy" ok={Boolean(preflight?.backend_healthy)} />
            <ChecklistRow label="Storage path writable" ok={Boolean(preflight?.storage_path_writable)} />
            <ChecklistRow label="Storage free space" ok={(preflight?.storage_free_bytes ?? 0) > 2_000_000_000} detail={bytesToHuman(preflight?.storage_free_bytes ?? 0)} />
            <ChecklistRow label="Webcam connected" ok={Boolean(preflight?.webcam_connected)} />
            <ChecklistRow label="Webcam preview" ok={Boolean(preflight?.webcam_preview_ok)} detail={`fps ${preflight?.webcam_fps?.toFixed(1) ?? "0.0"}`} />
            <ChecklistRow label="Required phones online" ok={requiredOnlineOk} detail={`${requiredOnlineCount}/${requiredBindings.length}`} />
                        <ChecklistRow label="Required role mapping" ok={requiredRoleCoverageOk} detail={`${requiredBindings.length}/${requiredRoles.length} assigned`} />
                        <ChecklistRow label="Required phones battery" ok={batteryOk} detail={`min ${MIN_BATTERY_PERCENT}%`} />
                        <ChecklistRow label="Required phones storage" ok={storageOk} detail={`min ${MIN_STORAGE_FREE_MB} MB`} />
            <ChecklistRow label="Clock sync quality" ok={(syncReport?.overall_sync_quality ?? "bad") !== "bad"} detail={syncReport?.overall_sync_quality ?? "unknown"} />
            <ChecklistRow label="Expected sampling 100 Hz" ok={expectedHzOk} detail={allDevicesWithHz ? "all devices >=95Hz" : "hz telemetry incomplete"} />
          </Panel>

          <Panel title="Devices" subtitle="Transport status + sampling quality trend (interval/jitter p99)">
            <div className="space-y-2">
              {devices.map((device) => (
                <div key={device.device_id} className="rounded-xl border border-black/10 bg-[#f8f1e6] p-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{device.device_id}</span>
                    <span className={`rounded-full px-2 py-0.5 ${device.connected ? "bg-[#d4f3df] text-[#245f3b]" : "bg-[#f7d6cc] text-[#8b3727]"}`}>
                      {device.connected ? "online" : "offline"}
                    </span>
                  </div>
                  <div className="mt-1 grid grid-cols-3 gap-2 text-[#5f4d39]">
                    <span>Role {device.device_role}</span>
                    <span>Battery {device.battery_percent ?? "-"}%</span>
                    <span>Hz {device.effective_hz?.toFixed(1) ?? "-"}</span>
                  </div>
                  {(() => {
                    const trend = samplingHistoryByDevice[device.device_id] ?? [];
                    const intervalSeries = trend.map((item) => item.interval_p99_ms).filter((item): item is number => typeof item === "number");
                    const jitterSeries = trend.map((item) => item.jitter_p99_ms).filter((item): item is number => typeof item === "number");
                    const intervalLine = sparkline(intervalSeries, 240, 40);
                    const jitterLine = sparkline(jitterSeries, 240, 40);
                    const latestInterval = trend.at(-1)?.interval_p99_ms ?? device.interval_p99_ms;
                    const latestJitter = trend.at(-1)?.jitter_p99_ms ?? device.jitter_p99_ms;
                    const quality = jitterQualityTone(latestJitter ?? null);
                    return (
                      <div className="mt-2 rounded-lg border border-black/10 bg-[#fffaf2] p-2">
                        <div className="mb-1 flex items-center justify-between">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[#5b4a37]">Sampling trend</p>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${quality.className}`}>
                            {quality.label}
                          </span>
                        </div>
                        <div className="grid gap-1 text-[11px] text-[#5f4d39]">
                          <div className="flex items-center justify-between">
                            <span>Interval p99</span>
                            <span>{latestInterval !== null && latestInterval !== undefined ? `${latestInterval.toFixed(2)} ms` : "-"}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span>Jitter p99</span>
                            <span>{latestJitter !== null && latestJitter !== undefined ? `${latestJitter.toFixed(2)} ms` : "-"}</span>
                          </div>
                        </div>
                        <svg viewBox="0 0 240 40" className="mt-2 h-10 w-full rounded-md bg-[#1b150f]">
                          <line x1="0" y1="20" x2="240" y2="20" stroke="#8f7653" strokeDasharray="4 4" strokeWidth="1" opacity="0.4" />
                          <polyline fill="none" stroke="#f0a36f" strokeWidth="2" points={intervalLine} />
                        </svg>
                        <svg viewBox="0 0 240 40" className="mt-1 h-10 w-full rounded-md bg-[#131911]">
                          <line x1="0" y1="20" x2="240" y2="20" stroke="#6f8b67" strokeDasharray="4 4" strokeWidth="1" opacity="0.4" />
                          <polyline fill="none" stroke="#8de37a" strokeWidth="2" points={jitterLine} />
                        </svg>
                        <p className="mt-1 text-[10px] text-[#6b5842]">
                          target interval {SAMPLING_TARGET_INTERVAL_MS} ms, history {trend.length} titik
                        </p>
                      </div>
                    );
                  })()}
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Video + Sync" subtitle="Recorder state, start barrier, clock report">
            <div className="space-y-2 text-sm">
              <div className="rounded-xl border border-black/10 bg-[#f8f1e6] p-3">
                <p>Video status: <strong>{video?.status ?? "idle"}</strong></p>
                <p>Backend: {video?.backend ?? "-"}</p>
                <p>Elapsed video: {secondsToClock(videoElapsedSeconds)}</p>
                <p>Dropped frame estimate: {video?.dropped_frame_estimate ?? 0}</p>
                <p>Webcam preview: {preflight?.webcam_preview_ok ? "ready sebelum record" : "not ready"}</p>
                <Image
                  src={webcamSnapshot}
                  alt="Webcam snapshot"
                  width={640}
                  height={360}
                  unoptimized
                  className="mt-2 h-32 w-full rounded-lg border border-black/10 object-cover"
                  onError={() => {
                    setInfo("Webcam snapshot endpoint belum tersedia / kamera tidak bisa dibaca");
                  }}
                />
                <p className="mt-1 text-xs text-[#6f5a45]">Preview menggunakan snapshot JPEG periodik dari backend.</p>
              </div>
              <div className="rounded-xl border border-black/10 bg-[#f8f1e6] p-3">
                <p>Sync quality: <strong>{syncReport?.overall_sync_quality ?? "unknown"}</strong></p>
                <p>Start barrier ns: {startBarrierUnixNs ?? 0}</p>
                <label className="mt-2 flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={anonymizeMode} onChange={(event) => setAnonymizeMode(event.target.checked)} />
                  <span>Anonymize saat stop/finalize</span>
                </label>
                <button
                  onClick={() => selectedSession && void runAction("Anonymize started", async () => {
                    await runAnonymize(selectedSession);
                    await reloadSessionData();
                  })}
                  className="mt-2 rounded-lg bg-[#201911] px-2 py-1 text-xs text-white"
                >
                  Anonymize Now
                </button>
                <p className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${statusBadge(anonymizeState)}`}>
                  anonymize: {anonymizeState}
                </p>
                {anonymizeResult ? (
                  <div className="mt-2 rounded-lg border border-black/10 bg-[#fffdf9] p-2 text-xs">
                    <p>source: {anonymizeResult.source_file_path}</p>
                    <p>output: {anonymizeResult.output_file_path ?? "-"}</p>
                    <p>metadata: {anonymizeResult.metadata_file_path ?? "-"}</p>
                    <p>faces blurred: {anonymizeResult.faces_blurred}</p>
                  </div>
                ) : null}
                {videoMetadata ? (
                  <div className="mt-2 rounded-lg border border-black/10 bg-[#fffdf9] p-2 text-xs">
                    <p>codec: {videoMetadata.codec}</p>
                    <p>size: {videoMetadata.width}x{videoMetadata.height} @ {videoMetadata.fps.toFixed(1)} fps</p>
                    <p>metadata file: {videoMetadata.file_path}</p>
                  </div>
                ) : null}
              </div>
            </div>
          </Panel>
        </section>

        <section className="grid gap-4 xl:col-span-2 xl:grid-cols-2">
          <Panel title="Realtime Graph Area" subtitle="Rolling window preview dari event SENSOR_PREVIEW">
            <div className="space-y-3">
              {Object.entries(previewByDevice).length === 0 ? <p className="text-sm text-[#6f5b45]">Belum ada preview stream.</p> : null}
              {Object.entries(previewByDevice).map(([deviceId, points]) => {
                const accXLine = sparkline(points.map((item) => item.accX));
                const accYLine = sparkline(points.map((item) => item.accY));
                const accZLine = sparkline(points.map((item) => item.accZ));
                const gyroXLine = sparkline(points.map((item) => item.gyroX));
                const gyroYLine = sparkline(points.map((item) => item.gyroY));
                const gyroZLine = sparkline(points.map((item) => item.gyroZ));
                const hz = devices.find((item) => item.device_id === deviceId)?.effective_hz;
                return (
                  <div key={deviceId} className="rounded-xl border border-black/10 bg-[#fffdf9] p-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#6f5a45]">
                      {deviceId} / Hz {hz?.toFixed(1) ?? "-"}
                    </p>
                    <svg viewBox="0 0 280 84" className="h-24 w-full rounded-md bg-[#1d160f]">
                      <polyline fill="none" stroke="#f0a36f" strokeWidth="2" points={accXLine} />
                      <polyline fill="none" stroke="#9ae56f" strokeWidth="2" points={accYLine} />
                      <polyline fill="none" stroke="#f66f83" strokeWidth="2" points={accZLine} />
                    </svg>
                    <svg viewBox="0 0 280 84" className="mt-2 h-24 w-full rounded-md bg-[#111a1d]">
                      <polyline fill="none" stroke="#6fe8d8" strokeWidth="2" points={gyroXLine} />
                      <polyline fill="none" stroke="#7fb4ff" strokeWidth="2" points={gyroYLine} />
                      <polyline fill="none" stroke="#f4d96b" strokeWidth="2" points={gyroZLine} />
                    </svg>
                    <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-[#6f5a45]">
                      <span>Acc X/Y/Z</span>
                      <span>Gyro X/Y/Z</span>
                      <span>Window 30s</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>

          <Panel title="Annotation Control + List" subtitle="Start/stop/edit/delete dengan live refresh">
            <div className="grid gap-2 md:grid-cols-3">
              <input value={newLabel} onChange={(event) => setNewLabel(event.target.value)} className="rounded-lg border border-black/20 px-2 py-1 text-sm" placeholder="label" />
              <input value={newNote} onChange={(event) => setNewNote(event.target.value)} className="rounded-lg border border-black/20 px-2 py-1 text-sm" placeholder="note" />
              <button
                onClick={() => selectedSession && void runAction("Annotation started", async () => {
                  await startAnnotation(selectedSession, { label: newLabel, notes: newNote || undefined });
                  await reloadSessionData();
                })}
                className="rounded-lg bg-[#1e1a13] px-2 py-1 text-sm text-white"
              >
                Start Annotation
              </button>
            </div>
            <p className="mt-2 text-xs text-[#6f5a45]">Active: {activeAnnotations.length}</p>
            <div className="mt-2 max-h-64 space-y-2 overflow-auto pr-1">
              {annotations.map((annotation) => (
                <div key={annotation.annotation_id} className="rounded-xl border border-black/10 bg-[#fffdf9] p-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold">{annotation.label}</p>
                    <span className={`rounded-full px-2 py-0.5 ${annotation.ended_at ? "bg-[#ddecd8] text-[#275f2a]" : "bg-[#ffe3ce] text-[#824622]"}`}>
                      {annotationStatusText(annotation)}
                    </span>
                  </div>
                  <p>{annotation.annotation_id}</p>
                  <p className="text-[#6e5a46]">{annotation.started_at} {annotation.ended_at ? `-> ${annotation.ended_at}` : ""}</p>
                                    <p className="text-[#6e5a46]">Duration: {annotationDurationText(annotation)}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {annotation.ended_at === null ? (
                      <button
                        onClick={() => selectedSession && void runAction("Annotation stopped", async () => {
                          await stopAnnotation(selectedSession, annotation.annotation_id);
                          await reloadSessionData();
                        })}
                        className="rounded-md bg-[#845341] px-2 py-1 text-white"
                      >
                        Stop
                      </button>
                    ) : null}
                    <button
                      onClick={() => void runAction("Annotation patched", async () => {
                        const nextLabel = globalThis.prompt("Label baru", annotation.label);
                        if (nextLabel === null || nextLabel.trim().length === 0) {
                          return;
                        }

                        const nextNotes = globalThis.prompt("Notes baru (kosongkan untuk null)", annotation.notes ?? "");
                        if (nextNotes === null) {
                          return;
                        }

                        const nextStartedAt = globalThis.prompt("Started at (ISO-8601)", annotation.started_at);
                        if (nextStartedAt === null || parseIsoTimestamp(nextStartedAt) === null) {
                          throw new Error("started_at harus format ISO-8601 valid");
                        }

                        const nextEndedAtInput = globalThis.prompt("Ended at (ISO-8601, kosongkan jika active)", annotation.ended_at ?? "");
                        if (nextEndedAtInput === null) {
                          return;
                        }
                        const normalizedEndedAt = nextEndedAtInput.trim();
                        if (normalizedEndedAt && parseIsoTimestamp(normalizedEndedAt) === null) {
                          throw new Error("ended_at harus format ISO-8601 valid");
                        }

                        await patchAnnotation(annotation.annotation_id, {
                          label: nextLabel.trim(),
                          notes: nextNotes.trim() ? nextNotes.trim() : undefined,
                          started_at: nextStartedAt,
                          ended_at: normalizedEndedAt ? normalizedEndedAt : null,
                        });
                        await reloadSessionData();
                      })}
                      className="rounded-md border border-black/20 px-2 py-1"
                    >
                      Edit Label/Time/Notes
                    </button>
                    <button
                      onClick={() => void runAction("Annotation deleted", async () => {
                        await deleteAnnotation(annotation.annotation_id);
                        await reloadSessionData();
                      })}
                      className="rounded-md border border-[#b66656] px-2 py-1 text-[#b0412f]"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </section>

        <section className="xl:col-span-2">
          <Panel title="Artifacts" subtitle="Manifest, export, file registry dari backend">
            <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
              {artifacts.map((artifact) => (
                <div key={artifact.id} className="rounded-xl border border-black/10 bg-[#fffdf9] p-3 text-xs">
                  <p className="font-semibold uppercase tracking-[0.14em]">{artifact.artifact_type}</p>
                  <p className="mt-1 break-all text-[#6f5a45]">{artifact.file_path}</p>
                  <p className="mt-2">exists: {String(artifact.exists)}</p>
                  <p>size: {bytesToHuman(artifact.size_bytes ?? 0)}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-xl border border-black/10 bg-[#f8f1e6] p-3 text-xs">
              <p className="font-semibold uppercase tracking-[0.12em]">Upload-to-FAMS instructions/status</p>
              <p className="mt-1">Dataset package: <span className={famsReady ? "text-[#1d6a39]" : "text-[#8b3727]"}>{famsReady ? "ready" : "not-ready"}</span></p>
              {uploadInstructions ? (
                <div className="mt-2 space-y-2 text-[#5f4d39]">
                  <p>Local zip: {uploadInstructions.export_zip_path}</p>
                  <p>Remote target: {uploadInstructions.remote_target}</p>
                  <p>Checksum SHA-256: <span className="font-mono">{uploadInstructions.checksum_sha256}</span></p>
                  <div className="rounded-lg border border-black/10 bg-[#fffdf9] p-2">
                    <p className="font-semibold">PowerShell command</p>
                    <p className="mt-1 break-all font-mono text-[11px]">{uploadInstructions.command_powershell}</p>
                  </div>
                  <div className="rounded-lg border border-black/10 bg-[#fffdf9] p-2">
                    <p className="font-semibold">Shell command</p>
                    <p className="mt-1 break-all font-mono text-[11px]">{uploadInstructions.command_shell}</p>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-[#8b3727]">Upload instruction belum tersedia (cek export zip).</p>
              )}
              <div className="mt-3 rounded-lg border border-black/10 bg-[#fffdf9] p-2">
                <p className="font-semibold">Archive upload status</p>
                <p className="mt-1">uploaded: {archiveUpload?.uploaded ? "yes" : "no"}</p>
                <p>uploaded_at: {archiveUpload?.uploaded_at ?? "-"}</p>
                <p>uploaded_by: {archiveUpload?.uploaded_by ?? "-"}</p>
                <p className="break-all">remote_path: {archiveUpload?.remote_path ?? "-"}</p>
                <p className="break-all">checksum: {archiveUpload?.checksum ?? "-"}</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <input
                    value={uploadedBy}
                    onChange={(event) => setUploadedBy(event.target.value)}
                    placeholder="uploaded by"
                    className="rounded-lg border border-black/20 px-2 py-1"
                  />
                  <input
                    value={remotePathInput}
                    onChange={(event) => setRemotePathInput(event.target.value)}
                    placeholder="remote path"
                    className="rounded-lg border border-black/20 px-2 py-1"
                  />
                </div>
                <button
                  onClick={() => selectedSession && uploadInstructions && void runAction("Archive marked as uploaded", async () => {
                    await markArchiveUploaded(selectedSession, {
                      uploaded_by: uploadedBy.trim() || "operator",
                      remote_path: remotePathInput.trim() || uploadInstructions.remote_target,
                      checksum: uploadInstructions.checksum_sha256,
                    });
                    await reloadSessionData();
                  })}
                  className="mt-2 rounded-lg bg-[#1e1a13] px-3 py-1.5 text-white"
                  disabled={!selectedSession || !uploadInstructions}
                >
                  Mark as uploaded
                </button>
              </div>
            </div>
          </Panel>
        </section>

        {showFinalizeIncompleteModal ? (
          <section className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
            <div className="w-full max-w-2xl rounded-2xl border border-black/20 bg-white p-4 shadow-2xl">
              <h3 className="font-display text-sm uppercase tracking-[0.2em] text-[#755f46]">Finalize Incomplete</h3>
              <p className="mt-1 text-sm text-[#5f4d39]">Review completeness report lalu isi alasan wajib sebelum confirm.</p>
              <div className="mt-3 max-h-64 space-y-1 overflow-auto rounded-lg border border-black/10 bg-[#f8f1e6] p-2 text-xs">
                <p className="font-semibold">Overall: {completeness?.complete ? "COMPLETE" : "INCOMPLETE"}</p>
                {completenessEntries.length === 0 ? <p>Tidak ada detail checks.</p> : null}
                {completenessEntries.map(([name, passed]) => (
                  <div key={name} className="flex items-center justify-between rounded-md bg-[#fffdf9] px-2 py-1">
                    <span>{name}</span>
                    <span className={passed ? "text-[#245f3b]" : "text-[#8b3727]"}>{passed ? "OK" : "FAIL"}</span>
                  </div>
                ))}
                {completeness?.detail ? (
                  <pre className="mt-2 overflow-auto rounded-md bg-[#1e1a13] p-2 text-[11px] text-[#f4ecdf]">{JSON.stringify(completeness.detail, null, 2)}</pre>
                ) : null}
              </div>
              <textarea
                value={finalizeIncompleteReason}
                onChange={(event) => setFinalizeIncompleteReason(event.target.value)}
                placeholder="Reason wajib diisi"
                className="mt-3 h-24 w-full rounded-lg border border-black/20 px-3 py-2 text-sm"
              />
              <div className="mt-3 flex items-center justify-end gap-2">
                <button
                  onClick={() => {
                    setShowFinalizeIncompleteModal(false);
                    setFinalizeIncompleteReason("");
                  }}
                  className="rounded-lg border border-black/20 px-3 py-1.5"
                >
                  Cancel
                </button>
                <button
                  onClick={() => selectedSession && void runAction("Session finalized incomplete", async () => {
                    await finalizeSessionWithReason(selectedSession, finalizeIncompleteReason.trim());
                    if (anonymizeMode) {
                      await runAnonymize(selectedSession);
                    }
                    setShowFinalizeIncompleteModal(false);
                    setFinalizeIncompleteReason("");
                    await reloadSessionData();
                  })}
                  disabled={!finalizeIncompleteReason.trim()}
                  className="rounded-lg bg-[#8b3727] px-3 py-1.5 text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Confirm Finalize Incomplete
                </button>
              </div>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}

function Panel({ title, subtitle, children }: Readonly<{ title: string; subtitle: string; children: React.ReactNode }>) {
  return (
    <section className="rounded-2xl border border-black/10 bg-white/90 p-4 shadow-[0_18px_50px_-35px_rgba(42,31,19,0.45)]">
      <h3 className="font-display text-sm uppercase tracking-[0.22em] text-[#755f46]">{title}</h3>
      <p className="mt-1 text-xs text-[#6f5a45]">{subtitle}</p>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function InfoPill({ title, value }: Readonly<{ title: string; value: string }>) {
  return (
    <div className="rounded-xl border border-black/10 bg-[#f8f1e6] px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.2em] text-[#6f5a45]">{title}</p>
      <p className="mt-1 truncate text-sm font-semibold">{value}</p>
    </div>
  );
}

function ChecklistRow({ label, ok, detail }: Readonly<{ label: string; ok: boolean; detail?: string }>) {
  return (
    <div className="mb-1 flex items-center justify-between gap-2 rounded-lg border border-black/10 bg-[#f8f1e6] px-2 py-1.5 text-xs">
      <span>{label}</span>
      <div className="flex items-center gap-2">
        {detail ? <span className="text-[#75644e]">{detail}</span> : null}
        <span className={`rounded-full px-2 py-0.5 font-semibold ${ok ? "bg-[#d4f3df] text-[#245f3b]" : "bg-[#f7d6cc] text-[#8b3727]"}`}>
          {ok ? "OK" : "Fail"}
        </span>
      </div>
    </div>
  );
}
