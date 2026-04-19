"use client";
import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from "react";
import { saveChunk, loadChunks, clearChunks } from "@/lib/video_backup";

export interface WebcamRecorderHandle {
  startRecording: (sessionId: string) => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
  isReady: boolean;
}

interface Props {
  onReady: (ok: boolean) => void;
}

const TIMESLICE_MS = 1000;
const CODEC_PRIORITY = [
  "video/webm;codecs=vp9,opus",
  "video/webm;codecs=vp8,opus",
  "video/webm",
];

const WebcamRecorder = forwardRef<WebcamRecorderHandle, Props>(({ onReady }, ref) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sessionRef = useRef<string>("");
  const chunkIndexRef = useRef(0);
  const [isRecording, setIsRecording] = useState(false);
  const [flashVisible, setFlashVisible] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.muted = true;
          await videoRef.current.play();
        }
        onReady(true);
      } catch {
        onReady(false);
      }
    })();

    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, [onReady]);

  useImperativeHandle(ref, () => ({
    isReady: !!streamRef.current,

    async startRecording(sessionId: string) {
      if (!streamRef.current) return;
      sessionRef.current = sessionId;
      chunkIndexRef.current = 0;

      const mime = CODEC_PRIORITY.find(m => MediaRecorder.isTypeSupported(m)) ?? "";
      const recorder = new MediaRecorder(streamRef.current, mime ? { mimeType: mime } : {});
      mediaRef.current = recorder;

      recorder.ondataavailable = async (e) => {
        if (e.data.size > 0) {
          await saveChunk(sessionId, chunkIndexRef.current++, e.data);
        }
      };

      recorder.start(TIMESLICE_MS);
      setIsRecording(true);

      // Sync flash — 100ms white overlay (CLAUDE.md §6)
      setFlashVisible(true);
      setTimeout(() => setFlashVisible(false), 100);
    },

    async stopRecording(): Promise<Blob | null> {
      const recorder = mediaRef.current;
      if (!recorder || recorder.state === "inactive") return null;

      await new Promise<void>(resolve => {
        recorder.onstop = () => resolve();
        recorder.stop();
      });

      setIsRecording(false);

      const chunks = await loadChunks(sessionRef.current);
      if (chunks.length === 0) return null;

      const blob = new Blob(chunks, { type: chunks[0].type || "video/webm" });
      await clearChunks(sessionRef.current);
      return blob;
    },
  }));

  return (
    <div className="relative w-full rounded overflow-hidden bg-black border border-[#30363d]">
      {/* Sync flash overlay */}
      {flashVisible && (
        <div className="absolute inset-0 bg-white z-10 pointer-events-none" />
      )}
      <video
        ref={videoRef}
        className="w-full aspect-video object-cover"
        playsInline
        muted
      />
      {isRecording && (
        <div className="absolute top-2 left-2 flex items-center gap-1 bg-black/60 rounded px-2 py-0.5 text-xs text-red-400">
          <span className="animate-pulse">●</span> REC
        </div>
      )}
    </div>
  );
});

WebcamRecorder.displayName = "WebcamRecorder";
export default WebcamRecorder;
