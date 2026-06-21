import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import "./globals.css";

export const metadata: Metadata = {
  title: "IMU Telemetry Dashboard",
  description: "Operator dashboard for IMU data collection sessions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={GeistSans.className}>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
