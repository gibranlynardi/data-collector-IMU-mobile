class SampleFrame {
  const SampleFrame({
    required this.timestampDeviceUnixNs,
    required this.elapsedMs,
    required this.accXG,
    required this.accYG,
    required this.accZG,
    required this.gyroXDeg,
    required this.gyroYDeg,
    required this.gyroZDeg,
  });

  final int timestampDeviceUnixNs;
  final int elapsedMs;
  final double accXG;
  final double accYG;
  final double accZG;
  final double gyroXDeg;
  final double gyroYDeg;
  final double gyroZDeg;
}
