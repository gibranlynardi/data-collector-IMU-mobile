import 'dart:async';
import 'dart:math';

import 'package:sensors_plus/sensors_plus.dart';

import '../models/sample_frame.dart';

typedef SampleCallback = void Function(SampleFrame frame);

abstract class SensorSamplerPort {
  bool get isRunning;
  void start({
    required int frequencyHz,
    int? logicalStartUnixNs,
    required SampleCallback onSample,
  });
  void stop();
}

class SensorSampler implements SensorSamplerPort {
  SensorSampler();

  static const double _gravity = 9.80665;
  static const double _radToDeg = 180.0 / pi;

  StreamSubscription<AccelerometerEvent>? _accSub;
  StreamSubscription<GyroscopeEvent>? _gyroSub;
  Timer? _ticker;
  Stopwatch? _sessionStopwatch;
  int? _logicalStartUnixNs;

  double _accX = 0;
  double _accY = 0;
  double _accZ = 0;
  double _gyroX = 0;
  double _gyroY = 0;
  double _gyroZ = 0;

  bool get isRunning => _ticker != null;

  void start({
    required int frequencyHz,
    int? logicalStartUnixNs,
    required SampleCallback onSample,
  }) {
    stop();
    final clampedHz = frequencyHz <= 0 ? 100 : frequencyHz;
    final intervalMs = (1000 / clampedHz).round().clamp(5, 1000);

    _sessionStopwatch = Stopwatch()..start();
    _logicalStartUnixNs = logicalStartUnixNs;

    _accSub = accelerometerEventStream().listen((event) {
      _accX = event.x;
      _accY = event.y;
      _accZ = event.z;
    });

    _gyroSub = gyroscopeEventStream().listen((event) {
      _gyroX = event.x;
      _gyroY = event.y;
      _gyroZ = event.z;
    });

    _ticker = Timer.periodic(Duration(milliseconds: intervalMs), (_) {
      final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
      final elapsedMs = _logicalStartUnixNs == null
          ? (_sessionStopwatch?.elapsedMilliseconds ?? 0)
          : ((nowNs - _logicalStartUnixNs!) ~/ 1000000).clamp(0, 1 << 31);
      onSample(
        SampleFrame(
          timestampDeviceUnixNs: nowNs,
          elapsedMs: elapsedMs,
          accXG: _accX / _gravity,
          accYG: _accY / _gravity,
          accZG: _accZ / _gravity,
          gyroXDeg: _gyroX * _radToDeg,
          gyroYDeg: _gyroY * _radToDeg,
          gyroZDeg: _gyroZ * _radToDeg,
        ),
      );
    });
  }

  void stop() {
    _ticker?.cancel();
    _ticker = null;

    _accSub?.cancel();
    _accSub = null;

    _gyroSub?.cancel();
    _gyroSub = null;

    _sessionStopwatch?.stop();
    _sessionStopwatch = null;
    _logicalStartUnixNs = null;
  }
}
