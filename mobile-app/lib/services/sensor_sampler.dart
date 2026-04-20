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
  Stopwatch? _sessionStopwatch;
  int? _logicalStartUnixNs;
  int _emitIntervalNs = 10 * 1000 * 1000;
  int? _nextEmitUnixNs;
  bool _hasAcc = false;
  bool _hasGyro = false;
  SampleCallback? _onSample;

  double _accX = 0;
  double _accY = 0;
  double _accZ = 0;
  double _gyroX = 0;
  double _gyroY = 0;
  double _gyroZ = 0;
  int _latestAccUnixNs = 0;
  int _latestGyroUnixNs = 0;

  bool get isRunning => _accSub != null || _gyroSub != null;

  void start({
    required int frequencyHz,
    int? logicalStartUnixNs,
    required SampleCallback onSample,
  }) {
    stop();
    final clampedHz = frequencyHz <= 0 ? 100 : frequencyHz;
    final intervalMs = (1000 / clampedHz).round().clamp(5, 1000);
    _emitIntervalNs = intervalMs * 1000 * 1000;
    _nextEmitUnixNs = null;
    _hasAcc = false;
    _hasGyro = false;
    _latestAccUnixNs = 0;
    _latestGyroUnixNs = 0;
    _onSample = onSample;

    _sessionStopwatch = Stopwatch()..start();
    _logicalStartUnixNs = logicalStartUnixNs;

    _accSub = accelerometerEventStream().listen((event) {
      _accX = event.x;
      _accY = event.y;
      _accZ = event.z;
      _hasAcc = true;
      _latestAccUnixNs = _extractEventTimestampUnixNs(event);
      _tryEmitSamples(_latestAccUnixNs);
    });

    _gyroSub = gyroscopeEventStream().listen((event) {
      _gyroX = event.x;
      _gyroY = event.y;
      _gyroZ = event.z;
      _hasGyro = true;
      _latestGyroUnixNs = _extractEventTimestampUnixNs(event);
      _tryEmitSamples(_latestGyroUnixNs);
    });
  }

  int _extractEventTimestampUnixNs(dynamic event) {
    final dynamic rawTimestamp = (event as dynamic).timestamp;
    if (rawTimestamp is DateTime) {
      return rawTimestamp.microsecondsSinceEpoch * 1000;
    }
    if (rawTimestamp is int) {
      if (rawTimestamp > 100000000000000000) {
        return rawTimestamp;
      }
      if (rawTimestamp > 100000000000000) {
        return rawTimestamp * 1000;
      }
      if (rawTimestamp > 100000000000) {
        return rawTimestamp * 1000000;
      }
    }
    return DateTime.now().microsecondsSinceEpoch * 1000;
  }

  void _tryEmitSamples(int triggerUnixNs) {
    if (!_hasAcc || !_hasGyro || _onSample == null) {
      return;
    }

    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
    final safeTriggerNs = max(triggerUnixNs, nowNs);
    _nextEmitUnixNs ??= safeTriggerNs;

    while (_nextEmitUnixNs != null && safeTriggerNs >= _nextEmitUnixNs!) {
      final sampleUnixNs = _nextEmitUnixNs!;
      final elapsedMs = _logicalStartUnixNs == null
          ? (_sessionStopwatch?.elapsedMilliseconds ?? 0)
          : ((sampleUnixNs - _logicalStartUnixNs!) ~/ 1000000).clamp(0, 1 << 31);

      _onSample!(
        SampleFrame(
          timestampDeviceUnixNs: sampleUnixNs,
          elapsedMs: elapsedMs,
          accXG: _accX / _gravity,
          accYG: _accY / _gravity,
          accZG: _accZ / _gravity,
          gyroXDeg: _gyroX * _radToDeg,
          gyroYDeg: _gyroY * _radToDeg,
          gyroZDeg: _gyroZ * _radToDeg,
        ),
      );
      _nextEmitUnixNs = _nextEmitUnixNs! + _emitIntervalNs;
    }
  }

  void stop() {
    _accSub?.cancel();
    _accSub = null;

    _gyroSub?.cancel();
    _gyroSub = null;

    _sessionStopwatch?.stop();
    _sessionStopwatch = null;
    _logicalStartUnixNs = null;
    _nextEmitUnixNs = null;
    _hasAcc = false;
    _hasGyro = false;
    _onSample = null;
  }
}
