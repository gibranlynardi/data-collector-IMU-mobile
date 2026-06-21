"use client";
import type { SessionState } from "@/lib/ws_client";

const GLOW: Record<SessionState, { c1: string; c2: string }> = {
  IDLE:       { c1: "rgba(56,72,99,0.30)",   c2: "rgba(34,211,238,0.10)" },
  PREFLIGHT:  { c1: "rgba(202,138,4,0.26)",  c2: "rgba(34,211,238,0.10)" },
  READY:      { c1: "rgba(34,211,238,0.28)", c2: "rgba(59,130,246,0.16)" },
  RECORDING:  { c1: "rgba(220,38,38,0.30)",  c2: "rgba(127,29,29,0.22)" },
  FINALIZING: { c1: "rgba(234,88,12,0.28)",  c2: "rgba(202,138,4,0.16)" },
  VALIDATING: { c1: "rgba(147,51,234,0.28)", c2: "rgba(59,130,246,0.16)" },
  ERROR:      { c1: "rgba(153,27,27,0.38)",  c2: "rgba(69,10,10,0.30)" },
};

export default function AmbientBackdrop({ state }: { state: SessionState }) {
  const g = GLOW[state] ?? GLOW.IDLE;
  return (
    <div aria-hidden className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
      <div
        className="ambient-fade absolute inset-0"
        style={{
          transition: "background 1000ms ease",
          background: `
            radial-gradient(60% 55% at 18% 12%, ${g.c1}, transparent 70%),
            radial-gradient(55% 50% at 85% 20%, ${g.c2}, transparent 72%),
            radial-gradient(70% 60% at 50% 115%, ${g.c1}, transparent 75%)
          `,
        }}
      />
      {/* subtle top vignette for depth */}
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(120% 90% at 50% 0%, transparent 55%, rgba(0,0,0,0.45))" }}
      />
    </div>
  );
}
