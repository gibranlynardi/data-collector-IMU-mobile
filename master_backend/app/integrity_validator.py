"""
Post-session integrity checks (CLAUDE.md §10, §22.8).
Phase 2: basic row count + SHA-256.
Phase 4: cross-device start drift, offline intervals, role uniqueness.
"""
import json
import time
from pathlib import Path

from .audit_logger import audit


class IntegrityValidator:
    async def run(
        self,
        session_id: str,
        file_results: dict,
        devices: list,
        scheduled_start_ms: int = 0,
    ) -> dict:
        report: dict = {
            "session_id": session_id,
            "status": "PASS",
            "validated_at_ms": int(time.time() * 1000),
            "devices": [],
            "cross_device_checks": {},
        }

        # ── Per-device checks ─────────────────────────────────────────────────
        for device_id, result in file_results.items():
            path = Path(result["path"])
            rows = result["rows"]
            sha = result["sha256"]

            dev_obj = next((d for d in devices if d.device_id == device_id), None)

            device_report = {
                "device_id": device_id,
                "role": dev_obj.device_role if dev_obj else "unknown",
                "csv_path": str(path),
                "row_count": rows,
                "csv_sha256": sha,
                "status": "PASS",
                "first_packet_ts": dev_obj.first_packet_ts if dev_obj else None,
                "offline_intervals": dev_obj.offline_intervals if dev_obj else [],
                "packets_received": dev_obj.packets_received if dev_obj else 0,
            }

            if rows == 0:
                device_report["status"] = "FAIL"
                device_report["issue"] = "zero rows written"
                report["status"] = "FAIL"

            # Flag sessions with offline intervals
            if dev_obj and dev_obj.offline_intervals:
                device_report["status"] = "PARTIAL"
                if report["status"] == "PASS":
                    report["status"] = "PARTIAL"

            report["devices"].append(device_report)

        # ── Cross-device checks (Phase 4, CLAUDE.md §22.8) ───────────────────
        if len(file_results) > 1 and scheduled_start_ms:
            first_timestamps = [
                d.first_packet_ts for d in devices
                if d.first_packet_ts is not None
            ]
            if first_timestamps:
                max_drift = max(first_timestamps) - min(first_timestamps)
                drift_ok = max_drift <= 100   # CLAUDE.md: < 100ms required
                if not drift_ok:
                    report["status"] = "FAIL"

                report["cross_device_checks"] = {
                    "max_start_drift_ms": max_drift,
                    "start_drift_ok": drift_ok,
                    "scheduled_start_ms": scheduled_start_ms,
                    "device_count": len(file_results),
                    "all_devices_completed": all(
                        r.get("row_count", 0) > 0 for r in file_results.values()
                    ),
                    "missing_devices_intervals": [
                        {
                            "device_id": d.device_id,
                            "role": d.device_role,
                            "intervals": d.offline_intervals,
                        }
                        for d in devices
                        if d.offline_intervals
                    ],
                }

        # Roles uniqueness check
        roles = [d.device_role for d in devices]
        report["cross_device_checks"]["role_uniqueness"] = (
            "pass" if len(roles) == len(set(roles)) else "fail"
        )

        # Write report
        if file_results:
            first_path = Path(list(file_results.values())[0]["path"])
            report_path = first_path.parent / f"{session_id}_integrity_report.json"
            try:
                report_path.write_text(json.dumps(report, indent=2))
            except OSError as exc:
                await audit.log("ERROR", "integrity_report_write_failed", {"error": str(exc)})

        return report
