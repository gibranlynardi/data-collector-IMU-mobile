import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/node_config.dart';

abstract class BackendClientPort {
  Future<void> registerDevice(NodeConfig config);
  Future<void> patchDeviceStatus({
    required NodeConfig config,
    required bool connected,
    required bool recording,
    double? batteryPercent,
    int? storageFreeMb,
    double? effectiveHz,
    double? intervalP99Ms,
    double? jitterP99Ms,
  });
  void close();
}

class BackendClient implements BackendClientPort {
  BackendClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<void> registerDevice(NodeConfig config) async {
    final uri = Uri.parse('${config.backendBaseUrl}/devices/register');
    final response = await _client
        .post(
          uri,
          headers: {
            'Content-Type': 'application/json',
            if (config.enrollmentToken.trim().isNotEmpty) 'X-Device-Enrollment-Token': config.enrollmentToken.trim(),
            if (config.deviceId.trim().isNotEmpty) 'X-Device-Id': config.deviceId.trim(),
          },
          body: jsonEncode({
            'device_id': config.deviceId,
            'device_role': config.deviceRole,
            'display_name': config.displayName,
          }),
        )
        .timeout(const Duration(seconds: 5));

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('register device gagal: ${response.statusCode} ${response.body}');
    }
  }

  Future<void> patchDeviceStatus({
    required NodeConfig config,
    required bool connected,
    required bool recording,
    double? batteryPercent,
    int? storageFreeMb,
    double? effectiveHz,
    double? intervalP99Ms,
    double? jitterP99Ms,
  }) async {
    final uri = Uri.parse('${config.backendBaseUrl}/devices/${config.deviceId}');
    final response = await _client
        .patch(
          uri,
          headers: {
            'Content-Type': 'application/json',
            if (config.enrollmentToken.trim().isNotEmpty) 'X-Device-Enrollment-Token': config.enrollmentToken.trim(),
            if (config.deviceId.trim().isNotEmpty) 'X-Device-Id': config.deviceId.trim(),
          },
          body: jsonEncode({
            'connected': connected,
            'recording': recording,
            'battery_percent': batteryPercent,
            'storage_free_mb': storageFreeMb,
            'effective_hz': effectiveHz,
            'interval_p99_ms': intervalP99Ms,
            'jitter_p99_ms': jitterP99Ms,
          }),
        )
        .timeout(const Duration(seconds: 5));

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('patch device gagal: ${response.statusCode} ${response.body}');
    }
  }

  void close() {
    _client.close();
  }
}
