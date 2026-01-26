import 'dart:async';
import 'dart:math';
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
  int _currentFrequency = 50; 

  static const double _gravity = 9.80665;
  static const double _radToDeg = 180.0 / pi;

  void start({int frequency = 50}) {
    if (isRunning && _currentFrequency == frequency) return;
    
    if (isRunning) stop();

    _currentFrequency = frequency;
    
    int intervalMs = (1000 / frequency).round();

    _accSub = accelerometerEventStream().listen((event) {
      _lastAx = event.x;
      _lastAy = event.y;
      _lastAz = event.z;
    });

    _gyroSub = gyroscopeEventStream().listen((event) {
      _lastGx = event.x;
      _lastGy = event.y;
      _lastGz = event.z;
    });

    _ticker = Timer.periodic(Duration(milliseconds: intervalMs), (_) {
      _emitPacket();
    });

    isRunning = true;
    print("Internal Sensors Started at $_currentFrequency Hz (Interval: ${intervalMs}ms)");
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
      accX: _lastAx / _gravity, 
      accY: _lastAy / _gravity, 
      accZ: _lastAz / _gravity,
      gyroX: _lastGx * _radToDeg, 
      gyroY: _lastGy * _radToDeg, 
      gyroZ: _lastGz * _radToDeg,
      timestamp: DateTime.now(),
    ));
  }
}