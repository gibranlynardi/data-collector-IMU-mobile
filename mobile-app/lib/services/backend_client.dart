import 'dart:convert';
import 'dart:developer' as developer;

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
  int _reqSeq = 0;

  static const String _tag = 'BackendClient';

  void _log(String msg) {
    developer.log(msg, name: _tag);
  }

  bool _isTransientNetworkError(Object e) {
    if (e is! http.ClientException) return false;
    final msg = e.message.toLowerCase();
    return msg.contains('broken pipe') ||
        msg.contains('connection closed') ||
        msg.contains('connection reset') ||
        msg.contains('connection terminated') ||
        msg.contains('software caused connection abort');
  }

  Future<http.Response> _sendWithRetry({
    required String label,
    required String method,
    required Uri uri,
    required Future<http.Response> Function() send,
    int? bodyLen,
  }) async {
    final reqId = ++_reqSeq;
    final sw = Stopwatch()..start();
    _log('[$reqId] $label $method $uri body=${bodyLen ?? 0}B');
    try {
      final r = await send().timeout(const Duration(seconds: 5));
      _log('[$reqId] $label OK status=${r.statusCode} took=${sw.elapsedMilliseconds}ms respLen=${r.body.length}');
      if (r.statusCode >= 400) {
        _log('[$reqId] $label SERVER-ERROR status=${r.statusCode} body=${r.body}');
      }
      return r;
    } catch (e, st) {
      final ms = sw.elapsedMilliseconds;
      if (_isTransientNetworkError(e)) {
        _log('[$reqId] $label TRANSIENT-NET-ERR after=${ms}ms err=$e -> retrying once');
        final sw2 = Stopwatch()..start();
        try {
          final r = await send().timeout(const Duration(seconds: 5));
          _log('[$reqId] $label RETRY-OK status=${r.statusCode} took=${sw2.elapsedMilliseconds}ms');
          return r;
        } catch (e2, st2) {
          _log('[$reqId] $label RETRY-FAIL after=${sw2.elapsedMilliseconds}ms err=$e2');
          developer.log('[$reqId] $label retry stack', name: _tag, error: e2, stackTrace: st2);
          rethrow;
        }
      }
      _log('[$reqId] $label FAIL after=${ms}ms err=$e (type=${e.runtimeType})');
      developer.log('[$reqId] $label stack', name: _tag, error: e, stackTrace: st);
      rethrow;
    }
  }

  Future<void> registerDevice(NodeConfig config) async {
    final uri = Uri.parse('${config.effectiveBaseUrl}/devices/register');
    final body = jsonEncode({
      'device_id': config.deviceId,
      'device_role': config.deviceRole,
      'display_name': config.displayName,
    });
    final headers = {
      'Content-Type': 'application/json',
      if (config.enrollmentToken.trim().isNotEmpty) 'X-Device-Enrollment-Token': config.enrollmentToken.trim(),
      if (config.deviceId.trim().isNotEmpty) 'X-Device-Id': config.deviceId.trim(),
    };
    final response = await _sendWithRetry(
      label: 'registerDevice',
      method: 'POST',
      uri: uri,
      bodyLen: body.length,
      send: () => _client.post(uri, headers: headers, body: body),
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
    double? intervalP99Ms,
    double? jitterP99Ms,
  }) async {
    final uri = Uri.parse('${config.effectiveBaseUrl}/devices/${config.deviceId}');
    final body = jsonEncode({
      'connected': connected,
      'recording': recording,
      'battery_percent': batteryPercent,
      'storage_free_mb': storageFreeMb,
      'effective_hz': effectiveHz,
      'interval_p99_ms': intervalP99Ms,
      'jitter_p99_ms': jitterP99Ms,
    });
    final headers = {
      'Content-Type': 'application/json',
      if (config.enrollmentToken.trim().isNotEmpty) 'X-Device-Enrollment-Token': config.enrollmentToken.trim(),
      if (config.deviceId.trim().isNotEmpty) 'X-Device-Id': config.deviceId.trim(),
    };
    _log('patchDeviceStatus payload connected=$connected recording=$recording '
        'battery=$batteryPercent storageMb=$storageFreeMb hz=$effectiveHz '
        'p99Interval=$intervalP99Ms p99Jitter=$jitterP99Ms');
    final response = await _sendWithRetry(
      label: 'patchDeviceStatus',
      method: 'PATCH',
      uri: uri,
      bodyLen: body.length,
      send: () => _client.patch(uri, headers: headers, body: body),
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('patch device gagal: ${response.statusCode} ${response.body}');
    }
  }

  void close() {
    _log('client.close()');
    _client.close();
  }
}
