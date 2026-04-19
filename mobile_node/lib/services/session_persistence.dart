import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

// Persists recording session state to survive process death (CLAUDE.md §9.2).
class SessionPersistence {
  static final SessionPersistence _instance = SessionPersistence._internal();
  factory SessionPersistence() => _instance;
  SessionPersistence._internal();

  static const _fileName = 'session_state.json';

  Future<File> _file() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/$_fileName');
  }

  Future<void> save({
    required String sessionId,
    required String deviceId,
    required String serverIp,
    required int clockOffsetMs,
    required int lastSequenceNumber,
    required String deviceRole,
  }) async {
    final f = await _file();
    final data = {
      'session_id': sessionId,
      'device_id': deviceId,
      'server_ip': serverIp,
      'clock_offset_ms': clockOffsetMs,
      'last_sequence_number': lastSequenceNumber,
      'device_role': deviceRole,
      'state': 'RECORDING',
      'saved_at_ms': DateTime.now().millisecondsSinceEpoch,
    };
    await f.writeAsString(jsonEncode(data));
  }

  Future<Map<String, dynamic>?> loadInterrupted() async {
    try {
      final f = await _file();
      if (!await f.exists()) return null;
      final raw = await f.readAsString();
      final data = jsonDecode(raw) as Map<String, dynamic>;
      if (data['state'] == 'RECORDING') return data;
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<void> clear() async {
    final f = await _file();
    if (await f.exists()) {
      final data = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
      data['state'] = 'IDLE';
      await f.writeAsString(jsonEncode(data));
    }
  }
}
