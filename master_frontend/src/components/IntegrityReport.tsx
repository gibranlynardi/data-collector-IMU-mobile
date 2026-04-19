"use client";

interface DeviceReport {
  device_id: string;
  csv_path: string;
  row_count: number;
  csv_sha256: string;
  status: "PASS" | "FAIL" | "PARTIAL";
  issue?: string;
}

interface Report {
  session_id: string;
  status: "PASS" | "FAIL" | "PARTIAL";
  validated_at_ms: number;
  devices: DeviceReport[];
}

const STATUS_STYLE: Record<string, string> = {
  PASS: "text-green-400 bg-green-950 border-green-800",
  FAIL: "text-red-400 bg-red-950 border-red-800",
  PARTIAL: "text-yellow-400 bg-yellow-950 border-yellow-800",
};

export default function IntegrityReport({ report }: { report: Report }) {
  return (
    <div className={`rounded border px-4 py-3 text-sm ${STATUS_STYLE[report.status] ?? STATUS_STYLE.PARTIAL}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-bold text-base">
          Integrity: {report.status}
        </span>
        <span className="text-xs opacity-60">
          {new Date(report.validated_at_ms).toLocaleTimeString()}
        </span>
      </div>

      <p className="text-xs opacity-70 mb-2">Session: {report.session_id}</p>

      <div className="space-y-2">
        {report.devices.map(d => (
          <div key={d.device_id} className="rounded bg-black/20 p-2 text-xs font-mono space-y-0.5">
            <div className="flex justify-between">
              <span className="text-gray-300">{d.device_id.slice(0, 8)}…</span>
              <span className={d.status === "PASS" ? "text-green-400" : "text-red-400"}>{d.status}</span>
            </div>
            <div className="text-gray-500">rows: {d.row_count.toLocaleString()}</div>
            {d.issue && <div className="text-red-400">⚠ {d.issue}</div>}
            <div className="text-gray-600 truncate">sha256: {d.csv_sha256.slice(0, 16)}…</div>
          </div>
        ))}
      </div>
    </div>
  );
}
