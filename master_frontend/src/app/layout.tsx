import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IMU Telemetry Dashboard",
  description: "Operator dashboard for IMU data collection sessions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0d1117] text-[#e6edf3]">{children}</body>
    </html>
  );
}
