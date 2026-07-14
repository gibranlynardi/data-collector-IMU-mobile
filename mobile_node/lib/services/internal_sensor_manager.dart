import 'dart:async';
import 'dart:math';
import 'package:flutter/foundation.dart';
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

  // Raw per-sensor liveness counters: incremented inside the platform stream
  // callbacks. A positive delta over a window proves real hardware events
  // arrived — the only reliable "is this sensor alive?" signal (resampled
  // ticker output cannot distinguish a dead-zero sensor from a still one).
  int _accEventCount = 0;
  int _gyroEventCount = 0;
  int _lastAccEventAtMs = 0;
  int _lastGyroEventAtMs = 0;

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
    // Register at exactly the output rate (e.g. 100 Hz ≤ 200 Hz), which stays
    // below the Android 12+ high-rate gate. SensorInterval.fastestInterval
    // (0 µs, >200 Hz) silently delivers zero events on many OEM devices.
    final samplingPeriod = Duration(milliseconds: intervalMs);

    _accSub = accelerometerEventStream(
      samplingPeriod: samplingPeriod,
    ).listen((e) {
      _lastAx = e.x;
      _lastAy = e.y;
      _lastAz = e.z;
      _accEventCount++;
      _lastAccEventAtMs = DateTime.now().millisecondsSinceEpoch;
    }, onError: (Object e) {
      // Surface platform failures instead of silently emitting flat zeros.
      debugPrint('InternalSensorManager: accelerometer stream error: $e');
    });

    _gyroSub = gyroscopeEventStream(
      samplingPeriod: samplingPeriod,
    ).listen((e) {
      _lastGx = e.x;
      _lastGy = e.y;
      _lastGz = e.z;
      _gyroEventCount++;
      _lastGyroEventAtMs = DateTime.now().millisecondsSinceEpoch;
    }, onError: (Object e) {
      debugPrint('InternalSensorManager: gyroscope stream error: $e');
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

  int get accEventCount => _accEventCount;
  int get gyroEventCount => _gyroEventCount;
  int get lastAccEventAtMs => _lastAccEventAtMs;
  int get lastGyroEventAtMs => _lastGyroEventAtMs;

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
