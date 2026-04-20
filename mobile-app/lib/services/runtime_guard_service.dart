import 'dart:io';

import 'package:flutter/services.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

abstract class RuntimeGuardPort {
  Future<void> enableRecordingGuard({required String sessionId, required String deviceId});
  Future<void> disableRecordingGuard();
  Future<bool> isBatteryOptimizationIgnored();
  Future<void> openBatteryOptimizationSettings();
}

class RuntimeGuardService implements RuntimeGuardPort {
  static const MethodChannel _channel = MethodChannel('imu_node/runtime');

  @override
  Future<void> enableRecordingGuard({required String sessionId, required String deviceId}) async {
    await WakelockPlus.enable();
    if (!Platform.isAndroid) {
      return;
    }

    try {
      await _channel.invokeMethod<void>('startForegroundMode', {
        'title': 'IMU Collector aktif',
        'text': '$deviceId merekam session $sessionId',
      });
    } catch (_) {
      // Keep sampling with wakelock even if foreground mode unavailable.
    }
  }

  @override
  Future<void> disableRecordingGuard() async {
    try {
      await WakelockPlus.disable();
    } catch (_) {
      // Ignore wakelock failures during shutdown.
    }

    if (!Platform.isAndroid) {
      return;
    }

    try {
      await _channel.invokeMethod<void>('stopForegroundMode');
    } catch (_) {
      // Ignore foreground stop failures.
    }
  }

  @override
  Future<bool> isBatteryOptimizationIgnored() async {
    if (!Platform.isAndroid) {
      return true;
    }

    try {
      final result = await _channel.invokeMethod<bool>('isBatteryOptimizationIgnored');
      return result ?? false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> openBatteryOptimizationSettings() async {
    if (!Platform.isAndroid) {
      return;
    }
    await _channel.invokeMethod<void>('openBatteryOptimizationSettings');
  }
}
