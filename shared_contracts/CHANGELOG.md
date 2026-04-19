# Shared Contracts Changelog

## schema_version = 1 (2026-04-19)

Initial schema definition.

### sensor_packet.proto
- `SensorPacket`: acc_x/y/z (g), gyro_x/y/z (deg/s), timestamp_ms, sequence_number, device_id, schema_version, raw_timestamp_ms
- `DeviceRegister`: device_id, device_role, device_model, android_version, app_version, schema_version

### commands.proto
- `CommandType` enum: PING, PONG, START_SESSION, STOP_SESSION, SET_LABEL, ACK, CLOCK_SYNC, ERROR_ALERT
- `Command`: type, payload (JSON string), issued_at_ms, command_id

---

### Bump rules (from CLAUDE.md §14)
- Adding optional field → no bump (proto backward-compatible)
- Changing field semantics → bump minor, document here
- Removing/renaming field → bump major, provide migration tool
