class SensorPacket {
  final double accX;
  final double accY;
  final double accZ;
  final double gyroX;
  final double gyroY;
  final double gyroZ;
  final DateTime timestamp;

  SensorPacket({
    required this.accX,
    required this.accY,
    required this.accZ,
    required this.gyroX,
    required this.gyroY,
    required this.gyroZ,
    required this.timestamp,
  });

  @override
  String toString() {
    return 'A[${accX.toStringAsFixed(2)}, ${accY.toStringAsFixed(2)}, ${accZ.toStringAsFixed(2)}] '
           'G[${gyroX.toStringAsFixed(2)}, ${gyroY.toStringAsFixed(2)}, ${gyroZ.toStringAsFixed(2)}]';
  }

  List<dynamic> toCsvRow(int location, int label) {
    return [
      timestamp.toIso8601String(),
      accX, 
      accY, 
      accZ,
      gyroX, 
      gyroY, 
      gyroZ,
      location, 
      label     
    ];
  }
}