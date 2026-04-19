class PendingSample {
  const PendingSample({
    required this.id,
    required this.sessionId,
    required this.deviceId,
    required this.deviceRole,
    required this.seq,
    required this.timestampDeviceUnixNs,
    required this.elapsedMs,
    required this.accXG,
    required this.accYG,
    required this.accZG,
    required this.gyroXDeg,
    required this.gyroYDeg,
    required this.gyroZDeg,
  });

  final int id;
  final String sessionId;
  final String deviceId;
  final String deviceRole;
  final int seq;
  final int timestampDeviceUnixNs;
  final int elapsedMs;
  final double accXG;
  final double accYG;
  final double accZG;
  final double gyroXDeg;
  final double gyroYDeg;
  final double gyroZDeg;

  static PendingSample fromRow(Map<String, Object?> row) {
    return PendingSample(
      id: row['id'] as int,
      sessionId: row['session_id'] as String,
      deviceId: row['device_id'] as String,
      deviceRole: row['device_role'] as String,
      seq: row['seq'] as int,
      timestampDeviceUnixNs: row['timestamp_device_unix_ns'] as int,
      elapsedMs: row['elapsed_ms'] as int,
      accXG: row['acc_x_g'] as double,
      accYG: row['acc_y_g'] as double,
      accZG: row['acc_z_g'] as double,
      gyroXDeg: row['gyro_x_deg'] as double,
      gyroYDeg: row['gyro_y_deg'] as double,
      gyroZDeg: row['gyro_z_deg'] as double,
    );
  }
}
