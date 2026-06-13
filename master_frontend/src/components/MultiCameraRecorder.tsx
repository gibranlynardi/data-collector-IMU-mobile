"use client";
import { useCallback, useEffect, useRef, useState, useImperativeHandle, forwardRef } from "react";
import { saveChunk, loadChunks, clearAllChunks } from "@/lib/video_backup";

// ── Public contract (consumed by page.tsx) ──────────────────────────────────
export interface CameraResult { camId: string; deviceId: string; label: string; blob: Blob; mime: string; }
export interface CameraStatus { ready: number; total: number; ok: boolean; }
export interface StopOutcome { results: CameraResult[]; missed: string[]; }
export interface MultiCameraRecorderHandle {
  startRecording: (sessionId: string) => Promise<void>;
  stopRecording: () => Promise<StopOutcome>;
}
interface Props {
  onStatusChange: (status: CameraStatus) => void;
  disabled: boolean; // true while RECORDING — lock camera selection
}

const MAX_CAMERAS = 5;
const TIMESLICE_MS = 1000;
// Prefer MP4 (H.264) where supported (Chrome/Edge ≥130, Safari); fall back to WebM so
// recording never fails. Video-only, so no audio codec needed. (Same list as before.)
const CODEC_PRIORITY = [
  "video/mp4;codecs=avc1.42E01E",
  "video/mp4",
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
];

interface ActiveCam { camId: string; deviceId: string; label: string; }
interface TileHandle {
  start: (sessionId: string) => Promise<void>;
  stop: () => Promise<CameraResult | null>;
}

// ── One physical camera: its own stream, preview, recorder, chunk index ──────
interface TileProps {
  camId: string;
  deviceId: string;
  label: string;
  register: (camId: string, handle: TileHandle | null) => void;
  onStatus: (camId: string, live: boolean) => void;
}

function CameraTile({ camId, deviceId, label, register, onStatus }: TileProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const sessionRef = useRef<string>("");
  const chunkIndexRef = useRef(0);
  const [isRecording, setIsRecording] = useState(false);
  const [flash, setFlash] = useState(false);
  const [detail, setDetail] = useState("opening…");

  // Open this camera's dedicated stream. Keyed on deviceId/camId — both fixed per slot,
  // and onStatus is stable, so this runs exactly once per tile (no reopen churn).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.muted = true;
          await videoRef.current.play().catch(() => {});
        }
        const s = stream.getVideoTracks()[0]?.getSettings();
        setDetail(s?.width ? `${s.width}×${s.height}` : "live");
        onStatus(camId, true);
      } catch (e) {
        // Fail loud: surface the failed camera so preflight blocks (CLAUDE.md "Fail Loud").
        if (!cancelled) { setDetail("open failed"); onStatus(camId, false); console.error(`cam ${camId} open failed`, e); }
      }
    })();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach(t => t.stop());
      streamRef.current = null;
      onStatus(camId, false);
    };
  }, [deviceId, camId, onStatus]);

  // start/stop read the latest stream/recorder via refs; the registered handle is stable.
  const startFn = async (sessionId: string) => {
    if (!streamRef.current) return;
    sessionRef.current = sessionId;
    chunkIndexRef.current = 0;
    const mime = CODEC_PRIORITY.find(m => MediaRecorder.isTypeSupported(m)) ?? "";
    const recorder = new MediaRecorder(streamRef.current, mime ? { mimeType: mime } : {});
    mediaRef.current = recorder;
    recorder.ondataavailable = async (e) => {
      if (e.data.size > 0) await saveChunk(sessionId, camId, chunkIndexRef.current++, e.data);
    };
    recorder.start(TIMESLICE_MS);
    setIsRecording(true);
    setFlash(true);                          // operator-facing sync cue (parity with old)
    setTimeout(() => setFlash(false), 100);
  };
  const stopFn = async (): Promise<CameraResult | null> => {
    const recorder = mediaRef.current;
    if (!recorder || recorder.state === "inactive") return null;
    await new Promise<void>(resolve => { recorder.onstop = () => resolve(); recorder.stop(); });
    setIsRecording(false);
    const chunks = await loadChunks(sessionRef.current, camId);
    if (chunks.length === 0) return null;
    const blob = new Blob(chunks, { type: chunks[0].type || "video/webm" });
    // Do NOT clear here — chunks stay in IndexedDB so footage survives a blocked/aborted
    // download. They are GC'd at the start of the NEXT session (see startRecording). [Finding A]
    return { camId, deviceId, label, blob, mime: blob.type };
  };
  const startRef = useRef(startFn); startRef.current = startFn;
  const stopRef = useRef(stopFn); stopRef.current = stopFn;

  // Register once per tile; methods always call the freshest closure via refs.
  useEffect(() => {
    register(camId, { start: (s) => startRef.current(s), stop: () => stopRef.current() });
    return () => register(camId, null);
  }, [camId, register]);

  return (
    <div className="relative rounded overflow-hidden bg-black border border-[#30363d]">
      {flash && <div className="absolute inset-0 bg-white z-10 pointer-events-none" />}
      <video ref={videoRef} className="w-full aspect-video object-cover" playsInline muted />
      <div className="absolute top-1 left-1 flex items-center gap-1 bg-black/60 rounded px-1.5 py-0.5 text-[10px] text-gray-200">
        {isRecording && <span className="animate-pulse text-red-400">●</span>}
        <span className="font-mono font-bold">{camId}</span>
        <span className="opacity-60 max-w-[90px] truncate">{label}</span>
      </div>
      <div className="absolute bottom-1 right-1 bg-black/60 rounded px-1 text-[10px] font-mono text-gray-400">
        {detail}
      </div>
    </div>
  );
}

// ── Manager: enumerate, select, aggregate readiness, fan out start/stop ──────
const MultiCameraRecorder = forwardRef<MultiCameraRecorderHandle, Props>(
  ({ onStatusChange, disabled }, ref) => {
    const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
    const [active, setActive] = useState<ActiveCam[]>([]);
    const [permError, setPermError] = useState("");
    const tilesRef = useRef<Map<string, TileHandle>>(new Map());
    const statusRef = useRef<Map<string, boolean>>(new Map());
    const activeRef = useRef<ActiveCam[]>([]);

    // Compute aggregate readiness from refs (so the callbacks below stay stable).
    const emitStatus = useCallback(() => {
      const total = activeRef.current.length;
      let ready = 0;
      activeRef.current.forEach(c => { if (statusRef.current.get(c.camId)) ready++; });
      onStatusChange({ ready, total, ok: total >= 1 && ready === total });
    }, [onStatusChange]);

    const handleTileStatus = useCallback((camId: string, live: boolean) => {
      statusRef.current.set(camId, live);
      emitStatus();
    }, [emitStatus]);

    const registerTile = useCallback((camId: string, h: TileHandle | null) => {
      if (h) tilesRef.current.set(camId, h); else tilesRef.current.delete(camId);
    }, []);

    // Mirror active → ref and re-emit status whenever the selection changes.
    useEffect(() => { activeRef.current = active; emitStatus(); }, [active, emitStatus]);

    // Enumerate cameras after unlocking labels with a one-shot probe permission.
    useEffect(() => {
      (async () => {
        try {
          const probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
          probe.getTracks().forEach(t => t.stop()); // release immediately before opening exact devices
        } catch (e) {
          setPermError("Camera permission denied");
          onStatusChange({ ready: 0, total: 0, ok: false });
          console.error("camera permission probe failed", e);
          return;
        }
        const devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "videoinput");
        setCameras(devs);
        // Auto-select first camera → parity with previous single-camera default.
        if (devs.length > 0) {
          setActive([{ camId: "cam1", deviceId: devs[0].deviceId, label: devs[0].label || "camera 1" }]);
        } else {
          onStatusChange({ ready: 0, total: 0, ok: false });
        }
      })();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const toggleCamera = (dev: MediaDeviceInfo) => {
      if (disabled) return; // cannot change selection during RECORDING
      setActive(prev => {
        const existing = prev.find(a => a.deviceId === dev.deviceId);
        if (existing) {
          statusRef.current.delete(existing.camId);
          tilesRef.current.delete(existing.camId);
          return prev.filter(a => a.deviceId !== dev.deviceId);
        }
        if (prev.length >= MAX_CAMERAS) return prev; // cap
        // assign the lowest free camId (cam1..cam5)
        let camId = `cam${MAX_CAMERAS}`;
        for (let i = 1; i <= MAX_CAMERAS; i++) {
          const c = `cam${i}`;
          if (!prev.some(a => a.camId === c)) { camId = c; break; }
        }
        return [...prev, { camId, deviceId: dev.deviceId, label: dev.label || camId }];
      });
    };

    useImperativeHandle(ref, () => ({
      // Fan out to all live tiles in the SAME callback → synchronized start.
      async startRecording(sessionId: string) {
        // Deferred-clear point: free the PREVIOUS session's backups now that a new session is
        // starting. Must finish before any tile starts writing chunks. [Finding A]
        await clearAllChunks();
        await Promise.all(Array.from(tilesRef.current.values()).map(t => t.start(sessionId)));
      },
      async stopRecording(): Promise<StopOutcome> {
        const entries = Array.from(tilesRef.current.entries());
        const raw = await Promise.all(entries.map(([, t]) => t.stop()));
        const results: CameraResult[] = [];
        const missed: string[] = [];
        raw.forEach((r, i) => { if (r !== null) results.push(r); else missed.push(entries[i][0]); });
        return { results, missed };
      },
    }), []);

    return (
      <div className="flex flex-col gap-2">
        {/* Selector */}
        <div className="text-[11px]">
          {permError
            ? <span className="text-red-400">{permError}</span>
            : <span className="text-gray-400">{active.length}/{MAX_CAMERAS} selected · {cameras.length} detected</span>}
        </div>
        <div className="space-y-1">
          {cameras.map((dev, i) => {
            const sel = active.find(a => a.deviceId === dev.deviceId);
            const capped = !sel && active.length >= MAX_CAMERAS;
            const lock = disabled || capped;
            return (
              <label
                key={dev.deviceId || i}
                className={`flex items-center gap-2 text-[11px] px-2 py-1 rounded border
                  ${sel ? "border-blue-600 bg-blue-950/40 text-white" : "border-[#30363d] text-gray-400"}
                  ${lock ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:border-blue-500"}`}
              >
                <input
                  type="checkbox"
                  className="accent-blue-600"
                  checked={!!sel}
                  disabled={lock}
                  onChange={() => toggleCamera(dev)}
                />
                <span className="font-mono w-9">{sel ? sel.camId : "—"}</span>
                <span className="flex-1 truncate">{dev.label || `Camera ${i + 1}`}</span>
              </label>
            );
          })}
          {cameras.length === 0 && !permError && (
            <p className="text-[11px] text-gray-600 italic">No cameras detected</p>
          )}
        </div>

        {/* Live previews */}
        <div className="space-y-2">
          {active.map(c => (
            <CameraTile
              key={c.camId}
              camId={c.camId}
              deviceId={c.deviceId}
              label={c.label}
              register={registerTile}
              onStatus={handleTileStatus}
            />
          ))}
          {active.length === 0 && !permError && (
            <p className="text-[11px] text-gray-600 italic">Select at least one camera</p>
          )}
        </div>
      </div>
    );
  },
);
MultiCameraRecorder.displayName = "MultiCameraRecorder";
export default MultiCameraRecorder;
