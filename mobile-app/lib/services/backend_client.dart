import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/node_config.dart';

class BackendClient {
  BackendClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<void> registerDevice(NodeConfig config) async {
    final uri = Uri.parse('${config.backendBaseUrl}/devices/register');
    final response = await _client.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'device_id': config.deviceId,
        'device_role': config.deviceRole,
        'display_name': config.displayName,
      }),
    );

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
  }) async {
    final uri = Uri.parse('${config.backendBaseUrl}/devices/${config.deviceId}');
    final response = await _client.patch(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'connected': connected,
        'recording': recording,
        'battery_percent': batteryPercent,
        'storage_free_mb': storageFreeMb,
        'effective_hz': effectiveHz,
      }),
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('patch device gagal: ${response.statusCode} ${response.body}');
    }
  }

  void close() {
    _client.close();
  }
}
