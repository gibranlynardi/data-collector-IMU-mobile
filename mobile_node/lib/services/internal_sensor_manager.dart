import 'dart:async';
import 'dart:math';
import 'package:sensors_plus/sensors_plus.dart';
import '../models/sensor_packet.dart';

class InternalSensorManager {
  static final InternalSensorManager _instance =
      InternalSensorManager._internal();
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
  int _currentFrequency = 100;

  static const double _gravity = 9.80665;
  static const double _radToDeg = 180.0 / pi;

  void start({int frequency = 100}) {
    if (isRunning && _currentFrequency == frequency) return;
    if (isRunning) stop();

    _currentFrequency = frequency;
    final intervalMs = (1000 / frequency).round();

    _accSub = accelerometerEventStream().listen((e) {
      _lastAx = e.x;
      _lastAy = e.y;
      _lastAz = e.z;
    });

    _gyroSub = gyroscopeEventStream().listen((e) {
      _lastGx = e.x;
      _lastGy = e.y;
      _lastGz = e.z;
    });

    _ticker = Timer.periodic(Duration(milliseconds: intervalMs), (_) {
      _emitPacket();
    });

    isRunning = true;
  }

  void stop() {
    _accSub?.cancel();
    _gyroSub?.cancel();
    _ticker?.cancel();
    isRunning = false;
  }

  // Returns the raw vector magnitude (g units) for preflight sanity check.
  double get currentAccMagnitude {
    final ax = _lastAx / _gravity;
    final ay = _lastAy / _gravity;
    final az = _lastAz / _gravity;
    return sqrt(ax * ax + ay * ay + az * az);
  }

  double get currentGyroMagnitude {
    final gx = _lastGx * _radToDeg;
    final gy = _lastGy * _radToDeg;
    final gz = _lastGz * _radToDeg;
    return sqrt(gx * gx + gy * gy + gz * gz);
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
