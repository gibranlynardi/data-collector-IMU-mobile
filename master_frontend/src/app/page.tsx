"use client";
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";

import { wsClient, type SessionState, type DeviceInfo, type StateUpdate } from "@/lib/ws_client";
import StatusBanner from "@/components/StatusBanner";
import SessionForm from "@/components/SessionForm";
import PreflightPanel from "@/components/PreflightPanel";
import LabelingPanel from "@/components/LabelingPanel";
import IntegrityReport from "@/components/IntegrityReport";
import DevicePanel from "@/components/DevicePanel";
// Direct import — dynamic() breaks forwardRef so camRef.current would be null.
import MultiCameraRecorder, {
  type MultiCameraRecorderHandle,
  type CameraStatus,
} from "@/components/MultiCameraRecorder";

// ECharts uses browser APIs — dynamic import keeps SSR safe.
const RealtimeChart = dynamic(() => import("@/components/RealtimeChart"), { ssr: false });

// ── Types ─────────────────────────────────────────────────────────────────────
type AppView = "connect" | "dashboard";
type Sample = { acc: number[]; gyro: number[]; ts: number };

export default function Home() {
  // Connection
  const [view, setView] = useState<AppView>("connect");
  const [backendIp, setBackendIp] = useState("192.168.1.100");
  const [isWsConnected, setIsWsConnected] = useState(false);
  const [connectError, setConnectError] = useState("");

  // Session state (mirrored from backend)
  const [sessionState, setSessionState] = useState<SessionState>("IDLE");
  const [sessionId, setSessionId] = useState("");
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [quorum, setQuorum] = useState<{ connected: number; roles: string[] }>({ connected: 0, roles: [] });
  const [integrityReport, setIntegrityReport] = useState<Record<string, unknown> | null>(null);

  // Session form
  const [subject, setSubject] = useState("");
  const [sessionTag, setSessionTag] = useState("");
  const [operator, setOperator] = useState("");

  // Sensor chart
  const [liveSamples, setLiveSamples] = useState<Record<string, Sample>>({});

  // Labeling
  const [activeLabel, setActiveLabel] = useState(0);
  const [labelError, setLabelError] = useState("");

  // Cameras (1–5, dynamic)
  const [camStatus, setCamStatus] = useState<CameraStatus>({ ready: 0, total: 0, ok: false });
  const camRef = useRef<MultiCameraRecorderHandle>(null);

  const isRecording = sessionState === "RECORDING";
  // Derive online count directly from devices — single source of truth.
  const onlineCount = devices.filter(d => d.is_online).length;
  const prefightAllPass =
    isWsConnected &&
    onlineCount > 0 &&
    subject.trim().length > 0 &&
    sessionTag.trim().length > 0 &&
    operator.trim().length > 0 &&
    camStatus.ok;

  // ── WS event subscriptions ─────────────────────────────────────────────────
  useEffect(() => {
    const unsub = wsClient.onMessage((msg) => {
      if (msg.type === "STATE_UPDATE") {
        const su = msg as StateUpdate & {
          quorum?: { connected: number; roles: string[] };
          scheduled_start_ms?: number;
        };
        setSessionState(su.state);
        setSessionId(su.session_id ?? "");
        if (su.devices && (su.devices.length > 0 || su.state !== "IDLE")) {
          setDevices(su.devices);
        }
        if (su.quorum) setQuorum(su.quorum);
        if (su.integrity_report) setIntegrityReport(su.integrity_report);

        // Coordinated webcam start (CLAUDE.md §22.5)
        if (su.state === "RECORDING" && su.scheduled_start_ms) {
          const delay = su.scheduled_start_ms - Date.now();
          setTimeout(() => {
            camRef.current?.startRecording(su.session_id || String(Date.now()));
          }, Math.max(0, delay));
        }
      }
    });
    const unsubLive = wsClient.onLive((samples) => setLiveSamples({ ...samples }));

    return () => { unsub(); unsubLive(); };
  }, []);

  // ── Auto-reconnect on mount ────────────────────────────────────────────────
  useEffect(() => {
    const saved = localStorage.getItem("backendIp");
    if (!saved) return;

    setBackendIp(saved);
    wsClient.connect(saved);

    let tries = 0;
    const poll = setInterval(() => {
      if (wsClient.isConnected) {
        clearInterval(poll);
        setIsWsConnected(true);
        setView("dashboard");
        wsClient.getState();
      } else if (++tries > 25) {
        clearInterval(poll);
        // Backend unreachable — stay on connect screen with IP pre-filled.
      }
    }, 200);

    return () => clearInterval(poll);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Connect ────────────────────────────────────────────────────────────────
  const handleConnect = () => {
    setConnectError("");
    wsClient.connect(backendIp);

    // Poll until WS opens (max 5s).
    let tries = 0;
    const poll = setInterval(() => {
      if (wsClient.isConnected) {
        clearInterval(poll);
        localStorage.setItem("backendIp", backendIp);
        setIsWsConnected(true);
        setView("dashboard");
        wsClient.getState();
      } else if (++tries > 25) {
        clearInterval(poll);
        setConnectError(`Cannot reach ${backendIp}:8000`);
      }
    }, 200);
  };

  // ── Session controls ───────────────────────────────────────────────────────
  const handleStart = async () => {
    setIntegrityReport(null);
    setActiveLabel(0);
    setLabelError("");
    try {
      await wsClient.startSession(subject, sessionTag, operator);
      // Webcam start is triggered by STATE_UPDATE with scheduled_start_ms
      // for coordinated sync with mobile devices (CLAUDE.md §22.5)
    } catch (e) {
      alert(`Start failed: ${e}`);
    }
  };

  const handleStop = async () => {
    try {
      const { results, missed } = (await camRef.current?.stopRecording()) ?? { results: [], missed: [] };
      // Release backend before downloads — a throw/hang in the download loop can no longer
      // leave the session stuck in RECORDING. [Finding B]
      await wsClient.stopSession("operator_stop");
      // One download per camera; extension matches each camera's actual container.
      for (const r of results) {
        const ext = r.mime.includes("mp4") ? "mp4" : "webm";
        _downloadBlob(r.blob, `${sessionId}_${r.camId}_video_sync.${ext}`);
        // Stagger so the browser doesn't drop concurrent downloads (one-time
        // "Allow multiple downloads" prompt the first time).
        await new Promise(res => setTimeout(res, 350));
      }
      if (results.length > 0) {
        const manifest = {
          session_id: sessionId,
          cameras: results.map(r => ({
            cam_id: r.camId,
            device_id: r.deviceId,
            browser_label: r.label,
            mime: r.mime,
            file: `${sessionId}_${r.camId}_video_sync.${r.mime.includes("mp4") ? "mp4" : "webm"}`,
          })),
        };
        const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: "application/json" });
        _downloadBlob(blob, `${sessionId}_cameras.json`);
      }
      // [Finding C] Surface cameras that produced no footage so the operator knows an angle is missing.
      if (missed.length > 0) alert(`Warning: ${missed.join(", ")} captured no footage and was not saved.`);
    } catch (e) {
      alert(`Stop failed: ${e}`);
    }
  };

  const handleLabel = async (id: number) => {
    setLabelError("");
    try {
      await wsClient.setLabel(id);
      setActiveLabel(id);
    } catch {
      setLabelError(`Label ${id} failed — retried 3×`);
    }
  };

  // ── Render: connect screen ─────────────────────────────────────────────────
  if (view === "connect") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-full max-w-sm space-y-4 p-8 rounded-xl bg-[#161b22] border border-[#30363d]">
          <h1 className="text-xl font-bold text-center">IMU Telemetry</h1>
          <p className="text-xs text-gray-500 text-center">Operator Dashboard</p>
          <div>
            <label className="text-xs text-gray-400">Backend IP</label>
            <input
              className="w-full mt-1 px-3 py-2 rounded bg-[#0d1117] border border-[#30363d] text-sm
                         focus:outline-none focus:border-blue-500"
              value={backendIp}
              onChange={e => setBackendIp(e.target.value)}
              placeholder="192.168.1.100"
            />
          </div>
          {connectError && <p className="text-xs text-red-400">{connectError}</p>}
          <button
            onClick={handleConnect}
            className="w-full py-2 rounded bg-blue-700 hover:bg-blue-600 font-bold text-sm transition-colors"
          >
            Connect
          </button>
          {isWsConnected && (
            <button
              onClick={() => setView("dashboard")}
              className="w-full py-2 rounded text-sm text-blue-400 hover:text-blue-300
                         border border-[#30363d] hover:border-blue-500 transition-colors"
            >
              ← Back to Dashboard
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Render: dashboard ──────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <StatusBanner state={sessionState} sessionId={sessionId} devices={devices} isWsConnected={isWsConnected} />

      <div className="flex flex-1 gap-0 overflow-hidden min-h-0">
        {/* Left panel */}
        <aside className="w-64 shrink-0 border-r border-[#30363d] flex flex-col gap-4 p-4 overflow-y-auto">
          <SessionForm
            subject={subject} setSubject={setSubject}
            sessionTag={sessionTag} setSessionTag={setSessionTag}
            operator={operator} setOperator={setOperator}
            disabled={isRecording}
          />
          <DevicePanel
            devices={devices}
            quorum={quorum}
            liveSamples={liveSamples}
            isRecording={isRecording}
          />
          <PreflightPanel
            isWsConnected={isWsConnected}
            devices={devices}
            subject={subject}
            sessionTag={sessionTag}
            operator={operator}
            camStatus={camStatus}
          />

          {/* Start / Stop button */}
          {!isRecording ? (
            <button
              onClick={handleStart}
              disabled={!prefightAllPass}
              className="w-full py-2 rounded font-bold text-sm bg-green-800 hover:bg-green-700
                         disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              ▶ START SESSION
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="w-full py-2 rounded font-bold text-sm bg-red-800 hover:bg-red-700 transition-colors"
            >
              ■ STOP SESSION
            </button>
          )}

          {/* Disconnect */}
          <button
            onClick={() => { wsClient.disconnect(); setView("connect"); setIsWsConnected(false); }}
            className="text-xs text-gray-600 hover:text-gray-400 underline text-center"
          >
            Disconnect
          </button>
        </aside>

        {/* Center: chart */}
        <main className="flex-1 flex flex-col gap-4 p-4 overflow-hidden min-h-0">
          <div className="flex-1 min-h-0">
            <RealtimeChart samples={liveSamples} devices={devices} />
          </div>

          {/* Label panel */}
          <div className="shrink-0">
            {labelError && <p className="text-xs text-red-400 mb-1">{labelError}</p>}
            <LabelingPanel
              activeLabel={activeLabel}
              onLabel={handleLabel}
              disabled={!isRecording}
            />
          </div>

          {/* Integrity report */}
          {integrityReport && (
            <div className="shrink-0">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">
                  Last Session Report
                </span>
                <button
                  onClick={() => setIntegrityReport(null)}
                  className="text-xs text-gray-600 hover:text-gray-300 px-2 py-0.5 rounded border border-[#30363d] hover:border-gray-500 transition-colors"
                >
                  ✕ Dismiss
                </button>
              </div>
              <div className="max-h-44 overflow-y-auto">
                <IntegrityReport report={integrityReport as unknown as Parameters<typeof IntegrityReport>[0]["report"]} />
              </div>
            </div>
          )}
        </main>

        {/* Right: cameras (1–5) */}
        <aside className="w-72 shrink-0 border-l border-[#30363d] p-4 flex flex-col gap-3 overflow-y-auto">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Cameras</h3>
            <span className={`text-[11px] font-bold ${camStatus.ok ? "text-green-400" : "text-red-400"}`}>
              {camStatus.ready}/{camStatus.total}
            </span>
          </div>
          <MultiCameraRecorder ref={camRef} onStatusChange={setCamStatus} disabled={isRecording} />
          {!camStatus.ok && (
            <p className="text-xs text-red-400">
              {camStatus.total === 0
                ? "Select at least one camera — required for recording"
                : `${camStatus.total - camStatus.ready} camera(s) not ready`}
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

function _downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
