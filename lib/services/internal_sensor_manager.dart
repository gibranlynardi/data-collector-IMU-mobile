import 'dart:async';
import 'package:sensors_plus/sensors_plus.dart';
import '../models/sensor_packet.dart';

class InternalSensorManager {
  static final InternalSensorManager _instance = InternalSensorManager._internal();
  factory InternalSensorManager() => _instance;
  InternalSensorManager._internal();

  final _streamController = StreamController<SensorPacket>.broadcast();
  Stream<SensorPacket> get dataStream => _streamController.stream;

  double _lastAx = 0, _lastAy = 0, _lastAz = 0;
  double _lastGx = 0, _lastGy = 0, _lastGz = 0;
  
  StreamSubscription? _accSub;
  StreamSubscription? _gyroSub;
  Timer? _ticker;
  bool isRunning = false;

  void start() {
    if (isRunning) return;
    _accSub = userAccelerometerEventStream().listen((event) {
      _lastAx = event.x;
      _lastAy = event.y;
      _lastAz = event.z;
    });

    _gyroSub = gyroscopeEventStream().listen((event) {
      _lastGx = event.x;
      _lastGy = event.y;
      _lastGz = event.z;
    });

    _ticker = Timer.periodic(const Duration(milliseconds: 20), (_) {
      _emitPacket();
    });

    isRunning = true;
    print("Internal Sensors Started (50Hz)");
  }

  void stop() {
    _accSub?.cancel();
    _gyroSub?.cancel();
    _ticker?.cancel();
    isRunning = false;
    print("Internal Sensors Stopped");
  }

  void _emitPacket() {
    _streamController.add(SensorPacket(
      accX: _lastAx, 
      accY: _lastAy, 
      accZ: _lastAz,
      gyroX: _lastGx, 
      gyroY: _lastGy, 
      gyroZ: _lastGz,
      timestamp: DateTime.now(),
    ));
  }
}