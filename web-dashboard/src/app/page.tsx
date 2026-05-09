"use client";

import Image from "next/image";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

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
type Tab = "command" | "live" | "devices" | "video" | "artifacts" | "preflight";

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
  if (status === "completed") return "bg-[color:var(--success-bg)] text-[color:var(--success-text)]";
  if (status === "failed") return "bg-[color:var(--danger-bg)] text-[color:var(--danger-text)]";
  if (status === "running" || status === "pending") return "bg-[color:var(--warning-bg)] text-[color:var(--warning-text)]";
  return "bg-[color:var(--surface-3)] text-[color:var(--text-muted)]";
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
  if (!annotation.ended_at) return "active";
  return annotation.auto_closed ? "auto-closed" : "closed";
}

function bytesToHuman(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
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
  if (!startMs) return "-";
  const endMs = annotation.ended_at ? parseIsoTimestamp(annotation.ended_at) : Date.now();
  if (!endMs || endMs < startMs) return "-";
  return secondsToClock((endMs - startMs) / 1000);
}

const MIN_BATTERY_PERCENT = 20;
const MIN_STORAGE_FREE_MB = 512;

function sparkline(points: number[], width = 280, height = 84): string {
  if (points.length === 0) return "";
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

function sharedSparkline(series: number[][], width = 600, height = 180): string[] {
  const flat = series.flat();
  if (flat.length === 0) return series.map(() => "");
  const min = Math.min(...flat);
  const max = Math.max(...flat);
  const span = Math.max(1e-6, max - min);
  return series.map((points) =>
    points
      .map((point, index) => {
        const x = (index / Math.max(1, points.length - 1)) * width;
        const y = height - ((point - min) / span) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" "),
  );
}

function buildSamplingHistoryStore(points: SamplingQualityPoint[]): DeviceSamplingHistoryStore {
  const bucket: DeviceSamplingHistoryStore = {};
  for (const point of points) {
    const key = point.device_id;
    if (!bucket[key]) bucket[key] = [];
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
    return { label: "unknown", className: "bg-[color:var(--surface-3)] text-[color:var(--text-muted)]" };
  }
  if (jitterP99Ms <= 3) return { label: "stable", className: "bg-[color:var(--success-bg)] text-[color:var(--success-text)]" };
  if (jitterP99Ms <= 6) return { label: "degrading", className: "bg-[color:var(--warning-bg)] text-[color:var(--warning-text)]" };
  return { label: "critical", className: "bg-[color:var(--danger-bg)] text-[color:var(--danger-text)]" };
}

const NAV_ITEMS: { id: Tab; label: string; icon: ReactNode }[] = [
  {
    id: "command",
    label: "Session Controls",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2" width="14" height="14" rx="3" />
        <path d="M5 7l2 2-2 2M10 11h3" />
      </svg>
    ),
  },
  {
    id: "live",
    label: "Live Capture",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 9c1-2 2-4 3-3s2 4 3 2 2-5 3-3 2 3 3 2" />
        <line x1="2" y1="16" x2="16" y2="16" />
      </svg>
    ),
  },
  {
    id: "devices",
    label: "Devices",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="5" y="1" width="8" height="14" rx="2" />
        <path d="M9 13v1" />
        <path d="M2 5h2M14 5h2M2 9h2M14 9h2" />
      </svg>
    ),
  },
  {
    id: "video",
    label: "Video & Sync",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="5" width="11" height="8" rx="2" />
        <path d="M12 8l5-3v8l-5-3V8Z" />
      </svg>
    ),
  },
  {
    id: "artifacts",
    label: "Artifacts",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 5h14v2H2zM3 7h12v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" />
        <path d="M7 11h4" />
      </svg>
    ),
  },
  {
    id: "preflight",
    label: "Preflight",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 2h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z" />
        <path d="M6 7l1.5 1.5L10 6M6 11h6" />
      </svg>
    ),
  },
];

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

  const [activeTab, setActiveTab] = useState<Tab>("live");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const activeTabRef = useRef<Tab>(activeTab);
  const [liveDeviceId, setLiveDeviceId] = useState("");
  const [liveSignalMode, setLiveSignalMode] = useState<"acc" | "gyro">("acc");

  const selectedSession = sessionId.trim();
  const activeAnnotations = annotations.filter((item) => !item.ended_at && !item.deleted);
  const wsBase = useMemo(() => buildWsBase(API_BASE, health?.ws_port ?? null), [health?.ws_port]);
  const webcamSnapshot = useMemo(() => `${webcamSnapshotUrl()}?t=${webcamFrameTick}`, [webcamFrameTick]);

  const elapsedSeconds = useMemo(() => {
    if (!session?.started_at) return 0;
    const start = Date.parse(session.started_at);
    const end = session.stopped_at ? Date.parse(session.stopped_at) : clockNow;
    return Math.max(0, (end - start) / 1000);
  }, [clockNow, session]);

  const videoElapsedSeconds = useMemo(() => {
    if (!video) return 0;
    if (video.elapsed_ms > 0) return Math.floor(video.elapsed_ms / 1000);
    if (videoMetadata?.duration_ms) return Math.floor(videoMetadata.duration_ms / 1000);
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

  const onlineDevices = useMemo(() => devices.filter((item) => item.connected).length, [devices]);
  const liveDeviceIds = useMemo(() => Object.keys(previewByDevice), [previewByDevice]);
  const activeLiveDeviceId = liveDeviceId || liveDeviceIds[0] || "";
  const livePoints = activeLiveDeviceId ? previewByDevice[activeLiveDeviceId] ?? [] : [];
  const liveHz = devices.find((item) => item.device_id === activeLiveDeviceId)?.effective_hz ?? null;

  const [accXLine, accYLine, accZLine] = useMemo(() => {
    const series = [
      livePoints.map((item) => item.accX),
      livePoints.map((item) => item.accY),
      livePoints.map((item) => item.accZ),
    ];
    return sharedSparkline(series, 640, 200);
  }, [livePoints]);

  const [gyroXLine, gyroYLine, gyroZLine] = useMemo(() => {
    const series = [
      livePoints.map((item) => item.gyroX),
      livePoints.map((item) => item.gyroY),
      livePoints.map((item) => item.gyroZ),
    ];
    return sharedSparkline(series, 640, 200);
  }, [livePoints]);

  const liveLines = liveSignalMode === "acc" ? [accXLine, accYLine, accZLine] : [gyroXLine, gyroYLine, gyroZLine];

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    if (!liveDeviceIds.length) {
      setLiveDeviceId("");
      return;
    }
    if (!liveDeviceId || !liveDeviceIds.includes(liveDeviceId)) {
      setLiveDeviceId(liveDeviceIds[0]);
    }
  }, [liveDeviceId, liveDeviceIds]);

  const allDevicesWithHz = useMemo(
    () => devices.length > 0 && devices.every((item) => item.effective_hz !== null),
    [devices],
  );
  const expectedHzOk = useMemo(
    () => allDevicesWithHz && devices.every((item) => Number(item.effective_hz) >= 95),
    [allDevicesWithHz, devices],
  );

  const requiredRoleCoverageOk = useMemo(() => {
    if (requiredRoles.length === 0) return false;
    const assignedRoles = new Set(requiredBindings.map((item) => item.device_role.toLowerCase()));
    return requiredRoles.every((role) => assignedRoles.has(role.toLowerCase()));
  }, [requiredBindings, requiredRoles]);

  const requiredDevices = useMemo(
    () =>
      requiredBindings
        .map((binding) => devices.find((device) => device.device_id === binding.device_id))
        .filter((item): item is DeviceResponse => Boolean(item)),
    [devices, requiredBindings],
  );

  const batteryOk = useMemo(
    () =>
      requiredDevices.length > 0 &&
      requiredDevices.every((item) => item.battery_percent !== null && item.battery_percent >= MIN_BATTERY_PERCENT),
    [requiredDevices],
  );

  const storageOk = useMemo(
    () =>
      requiredDevices.length > 0 &&
      requiredDevices.every((item) => item.storage_free_mb !== null && item.storage_free_mb >= MIN_STORAGE_FREE_MB),
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
    if (!selectedSession) return;

    const [sessionPayload, bindingPayload, annotationPayload, artifactPayload, syncPayload, videoPayload] =
      await Promise.all([
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

    const [uploadInstructionsPayload, archiveUploadPayload, completenessPayload, samplingQualityPayload] =
      await Promise.all([
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
    if (!selectedSession) throw new Error("Connect session terlebih dahulu");
    if (requiredRoles.length === 0) throw new Error("required roles tidak tersedia");

    const roleAssignments: SessionDeviceAssignItem[] = [];
    const lowerRequired = requiredRoles.map((item) => item.toLowerCase());
    for (const role of lowerRequired) {
      const matched = devices.find((item) => item.device_role.toLowerCase() === role);
      if (!matched) throw new Error(`Tidak ada device untuk role ${role}`);
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
        if (selectedSession) await reloadSessionData();
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    };
    void boot();
    return () => { alive = false; };
  }, [reloadBaseData, reloadSessionData, selectedSession]);

  useEffect(() => {
    const interval = globalThis.setInterval(() => {
      void reloadBaseData();
      if (selectedSession) void reloadSessionData();
    }, 5000);
    return () => globalThis.clearInterval(interval);
  }, [reloadBaseData, reloadSessionData, selectedSession]);

  useEffect(() => {
    const timer = globalThis.setInterval(() => setClockNow(Date.now()), 1000);
    return () => globalThis.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (activeTab !== "video") return;
    const timer = globalThis.setInterval(() => {
      setWebcamFrameTick((prev) => prev + 1);
    }, 2000);
    return () => globalThis.clearInterval(timer);
  }, [activeTab]);

  useEffect(() => {
    if (!selectedSession) return;

    const wsQuery = new URLSearchParams();
    if (OPERATOR_WS_TOKEN) wsQuery.set("operator_token", OPERATOR_WS_TOKEN);
    if (OPERATOR_WS_ID) wsQuery.set("operator_id", OPERATOR_WS_ID);
    const wsSuffix = wsQuery.toString() ? `?${wsQuery.toString()}` : "";
    const ws = new WebSocket(`${wsBase}/ws/dashboard/${selectedSession}${wsSuffix}`);
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as DashboardEvent;
      if (payload.type === "SESSION_STATE") {
        setSession((prev) => (prev ? { ...prev, status: String(payload.status ?? prev.status) } : prev));
      }
      if (payload.type === "DASHBOARD_SNAPSHOT" && isJsonArray(payload.devices)) {
        setDevices((prev) => mergeDeviceSnapshot(prev, payload.devices as Array<Record<string, unknown>>));
      }
      if (payload.type === "SENSOR_PREVIEW" && activeTabRef.current === "live") {
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
          const next = [...current, { x: now, accX, accY, accZ, gyroX, gyroY, gyroZ }].filter(
            (item) => now - item.x <= PREVIEW_WINDOW_MS,
          );
          return { ...prev, [deviceId]: next };
        });
      }
      if (payload.type === "CLOCK_SYNC_STATUS") {
        setSyncReport((prev) =>
          prev
            ? {
                ...prev,
                overall_sync_quality: String(payload.overall_sync_quality ?? prev.overall_sync_quality),
                overall_sync_quality_color: String(
                  payload.overall_sync_quality_color ?? prev.overall_sync_quality_color,
                ),
                devices: Array.isArray(payload.devices)
                  ? (payload.devices as SyncReport["devices"])
                  : prev.devices,
              }
            : prev,
        );
      }
      if (payload.type === "VIDEO_RECORDER_STATUS") {
        setVideo((prev) => (prev ? { ...prev, status: String(payload.status ?? prev.status) } : prev));
      }
      if (payload.type === "SESSION_STOP_SYNCING") {
        setInfo(
          `SYNCING: pending ${(payload.pending_devices as string[] | undefined)?.join(", ") ?? "-"}`,
        );
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
        if (!deviceId || !measuredAt) return;
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
    ws.onerror = () => { setInfo("WS disconnected, fallback to polling"); };
    return () => { ws.close(); };
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

  const sessionStatusDot =
    session?.status === "running"
      ? "bg-[#35c27b] shadow-[0_0_6px_rgba(53,194,123,0.6)]"
      : session?.status === "stopped"
        ? "bg-[#f59e6b]"
        : session?.status === "finalized"
          ? "bg-[#94a3b8]"
          : "bg-[#475569]";

  return (
    <div className="flex min-h-dvh bg-[radial-gradient(120%_140%_at_0%_0%,#f8fafc_0%,#eef2f7_55%,#e2e8f0_100%)] text-[color:var(--foreground)]">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar ── */}
      <aside
        className={`fixed left-0 top-0 z-30 flex h-full w-56 flex-col bg-[color:var(--sidebar-bg)] shadow-[var(--shadow-sidebar)] transition-transform duration-300 ease-in-out lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        {/* Brand */}
        <div className="flex items-center justify-between border-b border-[color:var(--sidebar-border)] px-5 py-5">
          <div>
            <p className="font-display text-[10px] uppercase tracking-[0.45em] text-[color:var(--sidebar-muted)]">
              IMU Collector
            </p>
            <p className="mt-0.5 text-sm font-semibold leading-snug text-[color:var(--sidebar-text)]">
              Command Deck
            </p>
          </div>
          <button
            className="flex h-7 w-7 items-center justify-center rounded-lg text-[color:var(--sidebar-muted)] transition-colors hover:bg-white/10 hover:text-[color:var(--sidebar-text)] lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 3l10 10M13 3L3 13" />
            </svg>
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3" aria-label="Dashboard navigation">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => { setActiveTab(item.id); setSidebarOpen(false); }}
              className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150 ${
                activeTab === item.id
                  ? "bg-[color:var(--sidebar-accent-bg)] text-[color:var(--sidebar-text)] ring-1 ring-[color:rgba(47,111,237,0.45)]"
                  : "text-[color:var(--sidebar-muted)] hover:bg-[color:var(--sidebar-hover)] hover:text-[color:var(--sidebar-text)]"
              }`}
              aria-current={activeTab === item.id ? "page" : undefined}
            >
              <span
                className={`shrink-0 transition-colors ${
                  activeTab === item.id
                    ? "text-[color:var(--sidebar-accent)]"
                    : "text-[color:var(--sidebar-muted)] group-hover:text-[color:var(--sidebar-text)]"
                }`}
              >
                {item.icon}
              </span>
              {item.label}
              {item.id === "live" && activeAnnotations.length > 0 && (
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-[color:rgba(47,111,237,0.25)] px-1 text-[10px] font-semibold text-[#dbe7ff]">
                  {activeAnnotations.length}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Session status footer */}
        <div className="border-t border-[color:var(--sidebar-border)] px-4 py-4">
          <p className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--sidebar-muted)]">Session</p>
          <p className="mt-1 truncate font-mono text-xs text-[color:var(--sidebar-text)]">
            {selectedSession || "—"}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${sessionStatusDot}`} />
            <span className="text-xs text-[color:var(--sidebar-muted)]">{session?.status ?? "idle"}</span>
            <span className="ml-auto font-mono text-xs text-[color:var(--sidebar-muted)]">
              {secondsToClock(elapsedSeconds)}
            </span>
          </div>
          <p className="mt-2 text-[10px] text-[color:var(--sidebar-muted)]">
            REST {health?.rest_port ?? "—"} · WS {health?.ws_port ?? "—"}
          </p>
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="flex min-h-dvh w-full flex-col lg:pl-56">
        {/* Sticky top header */}
        <header className="sticky top-0 z-10 border-b border-[color:var(--stroke)] bg-[color:var(--surface)]/92 px-4 py-3 shadow-[var(--shadow-header)] backdrop-blur-sm lg:px-6">
          <div className="flex items-center gap-2">
            {/* Hamburger – mobile only */}
            <button
              className="mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-2)] lg:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
                <path d="M2 4h12M2 8h12M2 12h12" />
              </svg>
            </button>

            <input
              value={sessionIdInput}
              onChange={(event) => setSessionIdInput(event.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setSessionId(sessionIdInput.trim());
                  setSamplingHistoryByDevice({});
                }
              }}
              placeholder="20260419_143022_A1B2C3D4"
              className="min-w-0 flex-1 rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] px-3 py-2 text-sm shadow-[inset_0_1px_3px_rgba(15,23,42,0.08)] placeholder:text-[color:var(--text-faint)] focus:outline-none focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color:var(--accent)]"
            />
            <button
              onClick={() => {
                setSessionId(sessionIdInput.trim());
                setSamplingHistoryByDevice({});
              }}
              className="shrink-0 rounded-xl bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[color:var(--accent-strong)]"
            >
              Connect
            </button>
            <button
              onClick={() => {
                setSessionId("");
                setSessionIdInput("");
                setSamplingHistoryByDevice({});
              }}
              className="shrink-0 rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] px-3 py-2 text-sm text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-2)]"
            >
              Clear
            </button>
          </div>

          <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <InfoPill title="Session" value={selectedSession || "none"} />
            <InfoPill title="Status" value={session?.status ?? "idle"} />
            <InfoPill title="Elapsed" value={secondsToClock(elapsedSeconds)} />
            <InfoPill
              title="Start Barrier"
              value={countdownMs > 0 ? `${(countdownMs / 1000).toFixed(1)}s` : "ready"}
            />
          </div>

          {error ? (
            <p className="mt-2 rounded-lg bg-[color:var(--danger-bg)] px-3 py-2 text-sm text-[color:var(--danger-text)]">
              {error}
            </p>
          ) : null}
          {info !== "Dashboard ready" ? (
            <p className="mt-1 text-xs text-[color:var(--text-faint)]">{info}</p>
          ) : null}
        </header>

        {/* ── Tab content ── */}
        <main className="flex-1 p-4 lg:p-6">

          {/* ── Command tab ── */}
          {activeTab === "command" && (
            <div className="max-w-lg">
              <Panel title="Session Controls" subtitle="Create, assign devices, start, stop, finalize">
                <div className="grid gap-2">
                  <input
                    value={overrideReason}
                    onChange={(event) => setOverrideReason(event.target.value)}
                    placeholder="override reason (optional)"
                    className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] px-3 py-2 text-sm"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() =>
                        void runAction("Session created", async () => {
                          const created = await createSession({
                            session_id: sessionIdInput || undefined,
                            override_reason: overrideReason || null,
                          });
                          setSessionId(created.session_id);
                          setSessionIdInput(created.session_id);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[color:var(--accent)] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[color:var(--accent-strong)]"
                    >
                      Create
                    </button>
                    <button
                      onClick={() =>
                        selectedSession && void runAction("Session devices assigned", autoAssignRequiredRoles)
                      }
                      className="rounded-xl border border-[color:var(--stroke)] px-3 py-2 text-sm font-medium text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-2)]"
                    >
                      Assign Required
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Session started", async () => {
                          await startSession(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[#1f8f5f] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#17724b]"
                    >
                      Start
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Stop requested", async () => {
                          if (anonymizeMode) {
                            const confirmed = globalThis.confirm(
                              "Toggle anonymize aktif. Jalankan anonymize setelah STOP?",
                            );
                            if (!confirmed) return;
                          }
                          await stopSession(selectedSession);
                          if (anonymizeMode) await runAnonymize(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[#b34141] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#982f2f]"
                    >
                      Stop
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Session finalized", async () => {
                          if (anonymizeMode) {
                            const confirmed = globalThis.confirm(
                              "Toggle anonymize aktif. Jalankan anonymize setelah FINALIZE?",
                            );
                            if (!confirmed) return;
                          }
                          await finalizeSession(selectedSession, false);
                          if (anonymizeMode) await runAnonymize(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[#9a7b3e] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#7c6231]"
                    >
                      Finalize
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Completeness checked", async () => {
                          const report = await fetchSessionCompleteness(selectedSession);
                          setCompleteness(report);
                          setShowFinalizeIncompleteModal(true);
                        })
                      }
                      className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] px-3 py-2 text-sm font-medium text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-3)]"
                    >
                      Finalize Incomplete
                    </button>
                  </div>
                </div>
              </Panel>
            </div>
          )}

          {/* ── Live Capture tab ── */}
          {activeTab === "live" && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <div className="space-y-4">
                <Panel title="Live Recording" subtitle="Realtime sensor preview + status ringkas">
                  <div className="flex flex-wrap items-center gap-4 text-xs text-[color:var(--text-faint)]">
                    <span>
                      Recording <span className="font-semibold text-[color:var(--foreground)]">{session?.status ?? "idle"}</span>
                    </span>
                    <span>
                      Devices Online <span className="font-semibold text-[color:var(--foreground)]">{onlineDevices}/{devices.length}</span>
                    </span>
                    <span>
                      Active Annotations <span className="font-semibold text-[color:var(--foreground)]">{activeAnnotations.length}</span>
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-faint)]">
                      Device
                    </span>
                    <select
                      value={activeLiveDeviceId}
                      onChange={(event) => setLiveDeviceId(event.target.value)}
                      disabled={!liveDeviceIds.length}
                      className="rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] px-2 py-1 text-sm text-[color:var(--foreground)]"
                    >
                      {liveDeviceIds.length === 0 ? (
                        <option value="">No devices</option>
                      ) : (
                        liveDeviceIds.map((deviceId) => (
                          <option key={deviceId} value={deviceId}>
                            {deviceId}
                          </option>
                        ))
                      )}
                    </select>
                    <div className="ml-auto flex items-center gap-3 text-[11px] text-[color:var(--text-faint)]">
                      <span>Hz {liveHz !== null ? liveHz.toFixed(1) : "-"}</span>
                      <span>Window 30s</span>
                    </div>
                  </div>

                  <div className="mt-2 inline-flex rounded-full border border-[color:var(--stroke)] bg-[color:var(--surface-2)] p-0.5 text-xs">
                    <button
                      onClick={() => setLiveSignalMode("acc")}
                      className={`rounded-full px-3 py-1 font-medium transition-colors ${
                        liveSignalMode === "acc"
                          ? "bg-[color:var(--surface)] text-[color:var(--foreground)]"
                          : "text-[color:var(--text-faint)]"
                      }`}
                    >
                      ACC
                    </button>
                    <button
                      onClick={() => setLiveSignalMode("gyro")}
                      className={`rounded-full px-3 py-1 font-medium transition-colors ${
                        liveSignalMode === "gyro"
                          ? "bg-[color:var(--surface)] text-[color:var(--foreground)]"
                          : "text-[color:var(--text-faint)]"
                      }`}
                    >
                      GYRO
                    </button>
                  </div>

                  <div className="mt-3 rounded-2xl border border-[color:var(--stroke)] bg-[#0b1220] p-3">
                    {livePoints.length === 0 ? (
                      <p className="text-sm text-[#a7b2c4]">Belum ada preview stream.</p>
                    ) : (
                      <svg viewBox="0 0 640 200" className="h-52 w-full">
                        <line x1="0" y1="50" x2="640" y2="50" stroke="#1f2937" strokeWidth="1" />
                        <line x1="0" y1="100" x2="640" y2="100" stroke="#1f2937" strokeWidth="1" />
                        <line x1="0" y1="150" x2="640" y2="150" stroke="#1f2937" strokeWidth="1" />
                        <polyline fill="none" stroke="#7fb4ff" strokeWidth="2" points={liveLines[0]} />
                        <polyline fill="none" stroke="#5fd6b5" strokeWidth="2" points={liveLines[1]} />
                        <polyline fill="none" stroke="#f4d96b" strokeWidth="2" points={liveLines[2]} />
                      </svg>
                    )}
                  </div>
                  <div className="mt-2 flex items-center gap-3 text-[10px] text-[color:var(--text-faint)]">
                    <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#7fb4ff]" />X</span>
                    <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#5fd6b5]" />Y</span>
                    <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#f4d96b]" />Z</span>
                  </div>
                </Panel>
              </div>
              <div className="space-y-4">
                <Panel title="Annotations" subtitle="Start/stop/edit/delete selama recording">
                  <div className="grid gap-2 sm:grid-cols-3">
                    <input
                      value={newLabel}
                      onChange={(event) => setNewLabel(event.target.value)}
                      className="rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] px-2 py-1.5 text-sm"
                      placeholder="label"
                    />
                    <input
                      value={newNote}
                      onChange={(event) => setNewNote(event.target.value)}
                      className="rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] px-2 py-1.5 text-sm"
                      placeholder="note"
                    />
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Annotation started", async () => {
                          await startAnnotation(selectedSession, {
                            label: newLabel,
                            notes: newNote || undefined,
                          });
                          await reloadSessionData();
                        })
                      }
                      className="rounded-lg bg-[color:var(--accent-strong)] px-2 py-1.5 text-sm text-white transition-colors hover:bg-[color:var(--accent)]"
                    >
                      Start Annotation
                    </button>
                  </div>
                  <p className="mt-2 text-xs text-[color:var(--text-faint)]">Active: {activeAnnotations.length}</p>
                  <div className="mt-3 max-h-[60vh] space-y-2 overflow-auto pr-1">
                    {annotations.length === 0 ? (
                      <p className="text-sm text-[color:var(--text-faint)]">Belum ada annotation.</p>
                    ) : null}
                    {annotations.map((annotation) => (
                      <div
                        key={annotation.annotation_id}
                        className="rounded-2xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-3 text-xs"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-semibold text-sm">{annotation.label}</p>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                              annotation.ended_at
                                ? "bg-[color:var(--success-bg)] text-[color:var(--success-text)]"
                                : "bg-[color:var(--warning-bg)] text-[color:var(--warning-text)]"
                            }`}
                          >
                            {annotationStatusText(annotation)}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[color:var(--text-muted)]">{annotation.annotation_id}</p>
                        <p className="text-[color:var(--text-muted)]">
                          {annotation.started_at}
                          {annotation.ended_at ? ` → ${annotation.ended_at}` : ""}
                        </p>
                        <p className="text-[color:var(--text-muted)]">Duration: {annotationDurationText(annotation)}</p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {annotation.ended_at === null ? (
                            <button
                              onClick={() =>
                                selectedSession &&
                                void runAction("Annotation stopped", async () => {
                                  await stopAnnotation(selectedSession, annotation.annotation_id);
                                  await reloadSessionData();
                                })
                              }
                              className="rounded-lg bg-[#b34141] px-2.5 py-1 text-xs text-white transition-colors hover:bg-[#982f2f]"
                            >
                              Stop
                            </button>
                          ) : null}
                          <button
                            onClick={() =>
                              void runAction("Annotation patched", async () => {
                                const nextLabel = globalThis.prompt("Label baru", annotation.label);
                                if (nextLabel === null || nextLabel.trim().length === 0) return;
                                const nextNotes = globalThis.prompt(
                                  "Notes baru (kosongkan untuk null)",
                                  annotation.notes ?? "",
                                );
                                if (nextNotes === null) return;
                                const nextStartedAt = globalThis.prompt(
                                  "Started at (ISO-8601)",
                                  annotation.started_at,
                                );
                                if (nextStartedAt === null || parseIsoTimestamp(nextStartedAt) === null) {
                                  throw new Error("started_at harus format ISO-8601 valid");
                                }
                                const nextEndedAtInput = globalThis.prompt(
                                  "Ended at (ISO-8601, kosongkan jika active)",
                                  annotation.ended_at ?? "",
                                );
                                if (nextEndedAtInput === null) return;
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
                              })
                            }
                            className="rounded-lg border border-[color:var(--stroke)] px-2.5 py-1 text-xs text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-2)]"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() =>
                              void runAction("Annotation deleted", async () => {
                                await deleteAnnotation(annotation.annotation_id);
                                await reloadSessionData();
                              })
                            }
                            className="rounded-lg border border-[color:var(--danger-text)] px-2.5 py-1 text-xs text-[color:var(--danger-text)] transition-colors hover:bg-[color:var(--danger-bg)]"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>

                <Panel title="Quick Actions" subtitle="Start/stop/finalize tanpa pindah tab">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Session started", async () => {
                          await startSession(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[#1f8f5f] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#17724b] disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!selectedSession}
                    >
                      Start
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Stop requested", async () => {
                          if (anonymizeMode) {
                            const confirmed = globalThis.confirm(
                              "Toggle anonymize aktif. Jalankan anonymize setelah STOP?",
                            );
                            if (!confirmed) return;
                          }
                          await stopSession(selectedSession);
                          if (anonymizeMode) await runAnonymize(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[#b34141] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#982f2f] disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!selectedSession}
                    >
                      Stop
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Session finalized", async () => {
                          if (anonymizeMode) {
                            const confirmed = globalThis.confirm(
                              "Toggle anonymize aktif. Jalankan anonymize setelah FINALIZE?",
                            );
                            if (!confirmed) return;
                          }
                          await finalizeSession(selectedSession, false);
                          if (anonymizeMode) await runAnonymize(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="rounded-xl bg-[#9a7b3e] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#7c6231] disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!selectedSession}
                    >
                      Finalize
                    </button>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Completeness checked", async () => {
                          const report = await fetchSessionCompleteness(selectedSession);
                          setCompleteness(report);
                          setShowFinalizeIncompleteModal(true);
                        })
                      }
                      className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] px-3 py-2 text-sm font-medium text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-3)] disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!selectedSession}
                    >
                      Finalize Incomplete
                    </button>
                  </div>
                  <p className="mt-2 text-xs text-[color:var(--text-faint)]">
                    Gunakan Session Controls untuk create session dan assign device.
                  </p>
                </Panel>
              </div>
            </div>
          )}

          {/* ── Preflight tab ── */}
          {activeTab === "preflight" && (
            <div className="max-w-xl">
              <Panel title="Preflight Checklist" subtitle="Backend + storage + webcam + required device readiness">
                <ChecklistRow label="Backend healthy" ok={Boolean(preflight?.backend_healthy)} />
                <ChecklistRow label="Storage path writable" ok={Boolean(preflight?.storage_path_writable)} />
                <ChecklistRow
                  label="Storage free space"
                  ok={(preflight?.storage_free_bytes ?? 0) > 2_000_000_000}
                  detail={bytesToHuman(preflight?.storage_free_bytes ?? 0)}
                />
                <ChecklistRow label="Webcam connected" ok={Boolean(preflight?.webcam_connected)} />
                <ChecklistRow
                  label="Webcam preview"
                  ok={Boolean(preflight?.webcam_preview_ok)}
                  detail={`fps ${preflight?.webcam_fps?.toFixed(1) ?? "0.0"}`}
                />
                <ChecklistRow
                  label="Required phones online"
                  ok={requiredOnlineOk}
                  detail={`${requiredOnlineCount}/${requiredBindings.length}`}
                />
                <ChecklistRow
                  label="Required role mapping"
                  ok={requiredRoleCoverageOk}
                  detail={`${requiredBindings.length}/${requiredRoles.length} assigned`}
                />
                <ChecklistRow
                  label="Required phones battery"
                  ok={batteryOk}
                  detail={`min ${MIN_BATTERY_PERCENT}%`}
                />
                <ChecklistRow
                  label="Required phones storage"
                  ok={storageOk}
                  detail={`min ${MIN_STORAGE_FREE_MB} MB`}
                />
                <ChecklistRow
                  label="Clock sync quality"
                  ok={(syncReport?.overall_sync_quality ?? "bad") !== "bad"}
                  detail={syncReport?.overall_sync_quality ?? "unknown"}
                />
                <ChecklistRow
                  label="Expected sampling 100 Hz"
                  ok={expectedHzOk}
                  detail={allDevicesWithHz ? "all devices >=95Hz" : "hz telemetry incomplete"}
                />
              </Panel>
            </div>
          )}

          {/* ── Devices tab ── */}
          {activeTab === "devices" && (
            <div className="max-w-3xl">
              <Panel title="Devices" subtitle="Transport status + sampling quality trend (interval/jitter p99)">
                <div className="space-y-3">
                  {devices.length === 0 ? (
                    <p className="text-sm text-[color:var(--text-faint)]">Belum ada device terdeteksi.</p>
                  ) : null}
                  {devices.map((device) => {
                    const trend = samplingHistoryByDevice[device.device_id] ?? [];
                    const intervalSeries = trend
                      .map((item) => item.interval_p99_ms)
                      .filter((item): item is number => typeof item === "number");
                    const jitterSeries = trend
                      .map((item) => item.jitter_p99_ms)
                      .filter((item): item is number => typeof item === "number");
                    const intervalLine = sparkline(intervalSeries, 240, 40);
                    const jitterLine = sparkline(jitterSeries, 240, 40);
                    const latestInterval = trend.at(-1)?.interval_p99_ms ?? device.interval_p99_ms;
                    const latestJitter = trend.at(-1)?.jitter_p99_ms ?? device.jitter_p99_ms;
                    const quality = jitterQualityTone(latestJitter ?? null);
                    return (
                      <div
                        key={device.device_id}
                        className="rounded-2xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] p-3 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm">{device.device_id}</span>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                              device.connected
                                ? "bg-[color:var(--success-bg)] text-[color:var(--success-text)]"
                                : "bg-[color:var(--danger-bg)] text-[color:var(--danger-text)]"
                            }`}
                          >
                            {device.connected ? "online" : "offline"}
                          </span>
                        </div>
                        <div className="mt-1.5 grid grid-cols-3 gap-2 text-[color:var(--text-muted)]">
                          <span>Role: {device.device_role}</span>
                          <span>Battery: {device.battery_percent ?? "-"}%</span>
                          <span>Hz: {device.effective_hz?.toFixed(1) ?? "-"}</span>
                        </div>
                        <div className="mt-2 rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-2">
                          <div className="mb-1.5 flex items-center justify-between">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[color:var(--text-muted)]">
                              Sampling trend
                            </p>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${quality.className}`}
                            >
                              {quality.label}
                            </span>
                          </div>
                          <div className="grid gap-1 text-[11px] text-[color:var(--text-muted)]">
                            <div className="flex items-center justify-between">
                              <span>Interval p99</span>
                              <span>
                                {latestInterval !== null && latestInterval !== undefined
                                  ? `${latestInterval.toFixed(2)} ms`
                                  : "-"}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span>Jitter p99</span>
                              <span>
                                {latestJitter !== null && latestJitter !== undefined
                                  ? `${latestJitter.toFixed(2)} ms`
                                  : "-"}
                              </span>
                            </div>
                          </div>
                          <svg viewBox="0 0 240 40" className="mt-2 h-10 w-full rounded-md bg-[#0b1220]">
                            <line
                              x1="0" y1="20" x2="240" y2="20"
                              stroke="#5c6b82" strokeDasharray="4 4" strokeWidth="1" opacity="0.4"
                            />
                            <polyline fill="none" stroke="#5b8cff" strokeWidth="2" points={intervalLine} />
                          </svg>
                          <svg viewBox="0 0 240 40" className="mt-1 h-10 w-full rounded-md bg-[#0b1a12]">
                            <line
                              x1="0" y1="20" x2="240" y2="20"
                              stroke="#4d6b5f" strokeDasharray="4 4" strokeWidth="1" opacity="0.4"
                            />
                            <polyline fill="none" stroke="#37d390" strokeWidth="2" points={jitterLine} />
                          </svg>
                          <p className="mt-1 text-[10px] text-[color:var(--text-faint)]">
                            target {SAMPLING_TARGET_INTERVAL_MS} ms · history {trend.length} titik
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Panel>
            </div>
          )}

          {/* ── Video & Sync tab ── */}
          {activeTab === "video" && (
            <div className="max-w-2xl space-y-4">
              <Panel title="Video Recorder" subtitle="Status, elapsed, webcam preview">
                <div className="space-y-2 text-sm">
                  <div className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] p-3">
                    <p>
                      Video status: <strong>{video?.status ?? "idle"}</strong>
                    </p>
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
                      className="mt-2 h-40 w-full rounded-xl border border-[color:var(--stroke)] object-cover"
                      onError={() => {
                        setInfo("Webcam snapshot endpoint belum tersedia / kamera tidak bisa dibaca");
                      }}
                    />
                    <p className="mt-1 text-xs text-[color:var(--text-faint)]">
                      Preview menggunakan snapshot JPEG periodik dari backend.
                    </p>
                    {videoMetadata ? (
                      <div className="mt-2 rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] p-2 text-xs">
                        <p>codec: {videoMetadata.codec}</p>
                        <p>
                          size: {videoMetadata.width}x{videoMetadata.height} @ {videoMetadata.fps.toFixed(1)} fps
                        </p>
                        <p>metadata file: {videoMetadata.file_path}</p>
                      </div>
                    ) : null}
                  </div>
                </div>
              </Panel>

              <Panel title="Clock Sync" subtitle="Start barrier, sync quality, anonymize">
                <div className="space-y-2 text-sm">
                  <div className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] p-3">
                    <p>
                      Sync quality: <strong>{syncReport?.overall_sync_quality ?? "unknown"}</strong>
                    </p>
                    <p>Start barrier ns: {startBarrierUnixNs ?? 0}</p>
                    <label className="mt-2 flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={anonymizeMode}
                        onChange={(event) => setAnonymizeMode(event.target.checked)}
                      />
                      <span>Anonymize saat stop/finalize</span>
                    </label>
                    <button
                      onClick={() =>
                        selectedSession &&
                        void runAction("Anonymize started", async () => {
                          await runAnonymize(selectedSession);
                          await reloadSessionData();
                        })
                      }
                      className="mt-2 rounded-lg bg-[color:var(--accent-strong)] px-3 py-1.5 text-xs text-white transition-colors hover:bg-[color:var(--accent)]"
                    >
                      Anonymize Now
                    </button>
                    <p
                      className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${statusBadge(anonymizeState)}`}
                    >
                      anonymize: {anonymizeState}
                    </p>
                    {anonymizeResult ? (
                      <div className="mt-2 rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] p-2 text-xs">
                        <p>source: {anonymizeResult.source_file_path}</p>
                        <p>output: {anonymizeResult.output_file_path ?? "-"}</p>
                        <p>metadata: {anonymizeResult.metadata_file_path ?? "-"}</p>
                        <p>faces blurred: {anonymizeResult.faces_blurred}</p>
                      </div>
                    ) : null}
                  </div>
                </div>
              </Panel>
            </div>
          )}

          {/* ── Artifacts tab ── */}
          {activeTab === "artifacts" && (
            <div className="max-w-4xl">
              <Panel title="Artifacts" subtitle="Manifest, export, file registry dari backend">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {artifacts.map((artifact) => (
                    <div
                      key={artifact.id}
                      className="rounded-2xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-3 text-xs"
                    >
                      <p className="font-semibold uppercase tracking-[0.14em]">{artifact.artifact_type}</p>
                      <p className="mt-1 break-all text-[color:var(--text-faint)]">{artifact.file_path}</p>
                      <p className="mt-2">exists: {String(artifact.exists)}</p>
                      <p>size: {bytesToHuman(artifact.size_bytes ?? 0)}</p>
                    </div>
                  ))}
                  {artifacts.length === 0 ? (
                    <p className="col-span-3 text-sm text-[color:var(--text-faint)]">Belum ada artifact.</p>
                  ) : null}
                </div>

                <div className="mt-4 rounded-2xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] p-4 text-xs">
                  <p className="font-semibold uppercase tracking-[0.12em]">Upload-to-FAMS</p>
                  <p className="mt-1">
                    Dataset package:{" "}
                    <span className={famsReady ? "text-[color:var(--success-text)]" : "text-[color:var(--danger-text)]"}>
                      {famsReady ? "ready" : "not-ready"}
                    </span>
                  </p>
                  {uploadInstructions ? (
                    <div className="mt-3 space-y-2 text-[color:var(--text-muted)]">
                      <p>Local zip: {uploadInstructions.export_zip_path}</p>
                      <p>Remote target: {uploadInstructions.remote_target}</p>
                      <p>
                        Checksum SHA-256:{" "}
                        <span className="font-mono">{uploadInstructions.checksum_sha256}</span>
                      </p>
                      <div className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-2">
                        <p className="font-semibold">PowerShell</p>
                        <p className="mt-1 break-all font-mono text-[11px]">
                          {uploadInstructions.command_powershell}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-2">
                        <p className="font-semibold">Shell</p>
                        <p className="mt-1 break-all font-mono text-[11px]">
                          {uploadInstructions.command_shell}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-2 text-[color:var(--danger-text)]">
                      Upload instruction belum tersedia (cek export zip).
                    </p>
                  )}

                  <div className="mt-4 rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-3">
                    <p className="font-semibold">Archive upload status</p>
                    <p className="mt-1">uploaded: {archiveUpload?.uploaded ? "yes" : "no"}</p>
                    <p>uploaded_at: {archiveUpload?.uploaded_at ?? "-"}</p>
                    <p>uploaded_by: {archiveUpload?.uploaded_by ?? "-"}</p>
                    <p className="break-all">remote_path: {archiveUpload?.remote_path ?? "-"}</p>
                    <p className="break-all">checksum: {archiveUpload?.checksum ?? "-"}</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <input
                        value={uploadedBy}
                        onChange={(event) => setUploadedBy(event.target.value)}
                        placeholder="uploaded by"
                        className="rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] px-2 py-1.5"
                      />
                      <input
                        value={remotePathInput}
                        onChange={(event) => setRemotePathInput(event.target.value)}
                        placeholder="remote path"
                        className="rounded-lg border border-[color:var(--stroke)] bg-[color:var(--surface)] px-2 py-1.5"
                      />
                    </div>
                    <button
                      onClick={() =>
                        selectedSession &&
                        uploadInstructions &&
                        void runAction("Archive marked as uploaded", async () => {
                          await markArchiveUploaded(selectedSession, {
                            uploaded_by: uploadedBy.trim() || "operator",
                            remote_path: remotePathInput.trim() || uploadInstructions.remote_target,
                            checksum: uploadInstructions.checksum_sha256,
                          });
                          await reloadSessionData();
                        })
                      }
                      className="mt-2 rounded-lg bg-[color:var(--accent-strong)] px-3 py-1.5 text-white transition-colors hover:bg-[color:var(--accent)] disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!selectedSession || !uploadInstructions}
                    >
                      Mark as uploaded
                    </button>
                  </div>
                </div>
              </Panel>
            </div>
          )}
        </main>
      </div>

      {/* ── Finalize Incomplete Modal ── */}
      {showFinalizeIncompleteModal ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="finalize-modal-title"
        >
          <div className="w-full max-w-2xl rounded-2xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-5 shadow-2xl">
            <h3
              id="finalize-modal-title"
              className="font-display text-sm uppercase tracking-[0.2em] text-[color:var(--text-muted)]"
            >
              Finalize Incomplete
            </h3>
            <p className="mt-1 text-sm text-[color:var(--text-muted)]">
              Review completeness report lalu isi alasan wajib sebelum confirm.
            </p>
            <div className="mt-3 max-h-64 space-y-1 overflow-auto rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] p-2 text-xs">
              <p className="font-semibold">Overall: {completeness?.complete ? "COMPLETE" : "INCOMPLETE"}</p>
              {completenessEntries.length === 0 ? <p>Tidak ada detail checks.</p> : null}
              {completenessEntries.map(([name, passed]) => (
                <div
                  key={name}
                  className="flex items-center justify-between rounded-lg bg-[color:var(--surface)] px-2 py-1"
                >
                  <span>{name}</span>
                  <span
                    className={passed ? "text-[color:var(--success-text)]" : "text-[color:var(--danger-text)]"}
                  >
                    {passed ? "OK" : "FAIL"}
                  </span>
                </div>
              ))}
              {completeness?.detail ? (
                <pre className="mt-2 overflow-auto rounded-lg bg-[#0f172a] p-2 text-[11px] text-[#e2e8f0]">
                  {JSON.stringify(completeness.detail, null, 2)}
                </pre>
              ) : null}
            </div>
            <textarea
              value={finalizeIncompleteReason}
              onChange={(event) => setFinalizeIncompleteReason(event.target.value)}
              placeholder="Reason wajib diisi"
              className="mt-3 h-24 w-full rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface)] px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color:var(--accent)]"
            />
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                onClick={() => {
                  setShowFinalizeIncompleteModal(false);
                  setFinalizeIncompleteReason("");
                }}
                className="rounded-xl border border-[color:var(--stroke)] px-4 py-2 text-sm text-[color:var(--text-muted)] transition-colors hover:bg-[color:var(--surface-2)]"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  selectedSession &&
                  void runAction("Session finalized incomplete", async () => {
                    await finalizeSessionWithReason(selectedSession, finalizeIncompleteReason.trim());
                    if (anonymizeMode) await runAnonymize(selectedSession);
                    setShowFinalizeIncompleteModal(false);
                    setFinalizeIncompleteReason("");
                    await reloadSessionData();
                  })
                }
                disabled={!finalizeIncompleteReason.trim()}
                className="rounded-xl bg-[#b34141] px-4 py-2 text-sm text-white transition-colors hover:bg-[#982f2f] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Confirm Finalize Incomplete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: Readonly<{ title: string; subtitle: string; children: ReactNode }>) {
  return (
    <section className="rounded-2xl border border-[color:var(--stroke)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-panel)]">
      <h2 className="font-display text-sm uppercase tracking-[0.22em] text-[color:var(--text-muted)]">{title}</h2>
      <p className="mt-1 text-xs text-[color:var(--text-faint)]">{subtitle}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function InfoPill({ title, value }: Readonly<{ title: string; value: string }>) {
  return (
    <div className="rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-faint)]">{title}</p>
      <p className="mt-0.5 truncate text-sm font-semibold text-[color:var(--foreground)]">{value}</p>
    </div>
  );
}

function ChecklistRow({
  label,
  ok,
  detail,
}: Readonly<{ label: string; ok: boolean; detail?: string }>) {
  return (
    <div className="mb-1.5 flex items-center justify-between gap-2 rounded-xl border border-[color:var(--stroke)] bg-[color:var(--surface-2)] px-3 py-2 text-xs">
      <span>{label}</span>
      <div className="flex items-center gap-2 shrink-0">
        {detail ? <span className="text-[color:var(--text-faint)]">{detail}</span> : null}
        <span
          className={`rounded-full px-2 py-0.5 font-semibold ${
            ok
              ? "bg-[color:var(--success-bg)] text-[color:var(--success-text)]"
              : "bg-[color:var(--danger-bg)] text-[color:var(--danger-text)]"
          }`}
        >
          {ok ? "OK" : "Fail"}
        </span>
      </div>
    </div>
  );
}
