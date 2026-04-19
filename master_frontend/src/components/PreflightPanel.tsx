"use client";
import type { DeviceInfo } from "@/lib/ws_client";

type CheckStatus = "pending" | "pass" | "fail";

interface Check { label: string; status: CheckStatus; detail?: string; }

function buildChecks(
  isWsConnected: boolean,
  devices: DeviceInfo[],
  subject: string,
  sessionTag: string,
  operator: string,
  webcamOk: boolean,
): Check[] {
  const onlineDevices = devices.filter(d => d.is_online);
  return [
    {
      label: "Backend connected",
      status: isWsConnected ? "pass" : "fail",
      detail: isWsConnected ? "OK" : "Not connected",
    },
    {
      label: "At least 1 device online",
      status: onlineDevices.length > 0 ? "pass" : "fail",
      detail: `${onlineDevices.length} online`,
    },
    {
      label: "Subject name",
      status: subject.trim().length > 0 ? "pass" : "fail",
      detail: subject || "Required",
    },
    {
      label: "Session tag",
      status: sessionTag.trim().length > 0 ? "pass" : "fail",
      detail: sessionTag || "Required",
    },
    {
      label: "Operator name",
      status: operator.trim().length > 0 ? "pass" : "fail",
      detail: operator || "Required",
    },
    {
      label: "Webcam available",
      status: webcamOk ? "pass" : "fail",
      detail: webcamOk ? "Ready" : "No camera detected",
    },
  ];
}

interface Props {
  isWsConnected: boolean;
  devices: DeviceInfo[];
  subject: string;
  sessionTag: string;
  operator: string;
  webcamOk: boolean;
}

export default function PreflightPanel(props: Props) {
  const checks = buildChecks(
    props.isWsConnected, props.devices,
    props.subject, props.sessionTag, props.operator, props.webcamOk,
  );
  const allPass = checks.every(c => c.status === "pass");

  return (
    <div>
      <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">
        Preflight {allPass ? "✓ GO" : "✗ NO-GO"}
      </h3>
      <div className="space-y-1">
        {checks.map(c => (
          <div key={c.label} className="flex items-center gap-2 text-xs">
            <span className={c.status === "pass" ? "text-green-400" : "text-red-400"}>
              {c.status === "pass" ? "✓" : "✗"}
            </span>
            <span className="text-gray-400 flex-1">{c.label}</span>
            <span className={`text-right ${c.status === "pass" ? "text-gray-500" : "text-red-400"}`}>
              {c.detail}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2">
        {props.devices.length > 0 && (
          <div className="text-xs text-gray-500 space-y-0.5">
            <p className="text-gray-400 font-semibold">Devices</p>
            {props.devices.map(d => (
              <div key={d.device_id} className="flex justify-between">
                <span className={d.is_online ? "text-green-400" : "text-gray-600"}>
                  {d.role}
                </span>
                <span className="text-gray-600">{d.packets.toLocaleString()} pkts</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export { buildChecks };
