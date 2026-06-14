// Single source of truth for per-role accent colors used by the live charts.
// Hues mirror DevicePanel.tsx's ROLE_COLOR Tailwind classes so the SAME node is the SAME
// color in the Devices panel and in the signal charts (visual consistency).
// (DevicePanel still uses Tailwind bg/border *classes*; aligning it to this hex map is a
//  future DRY cleanup — out of scope for this pass.)
export const ROLE_HEX: Record<string, string> = {
  chest:       "#3b82f6", // blue
  waist:       "#a855f7", // purple
  thigh_left:  "#22c55e", // green
  thigh_right: "#14b8a6", // teal
  ankle_left:  "#eab308", // yellow
  ankle_right: "#f97316", // orange
  wrist_left:  "#ec4899", // pink
  wrist_right: "#f43f5e", // rose
};

export const ROLE_HEX_FALLBACK = "#8b949e"; // gray for unknown roles

export function roleHex(role: string): string {
  return ROLE_HEX[role] ?? ROLE_HEX_FALLBACK;
}
