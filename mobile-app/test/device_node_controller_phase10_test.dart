import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sensors_app/generated/sensor_sample.pb.dart';
import 'package:sensors_app/models/node_config.dart';
import 'package:sensors_app/models/pending_sample.dart';
import 'package:sensors_app/models/sample_frame.dart';
import 'package:sensors_app/services/backend_client.dart';
import 'package:sensors_app/services/device_node_controller.dart';
import 'package:sensors_app/services/local_store.dart';
import 'package:sensors_app/services/node_config_store.dart';
import 'package:sensors_app/services/runtime_guard_service.dart';
import 'package:sensors_app/services/sensor_sampler.dart';
import 'package:sensors_app/services/socket_client.dart';

class _FakeConfigStore extends NodeConfigStore {
  _FakeConfigStore(this._config);

  NodeConfig _config;

  @override
  Future<NodeConfig> load() async => _config;

  @override
  Future<void> save(NodeConfig config) async {
    _config = config;
  }
}

class _FakeBackendClient implements BackendClientPort {
  int registerCalls = 0;

  @override
  Future<void> registerDevice(NodeConfig config) async {
    registerCalls += 1;
  }

  @override
  Future<void> patchDeviceStatus({required NodeConfig config, required bool connected, required bool recording, double? batteryPercent, int? storageFreeMb, double? effectiveHz, double? intervalP99Ms, double? jitterP99Ms}) async {}

  @override
  void close() {}
}

class _FakeSampler implements SensorSamplerPort {
  SampleCallback? _onSample;
  bool _running = false;

  @override
  bool get isRunning => _running;

  @override
  void start({required int frequencyHz, int? logicalStartUnixNs, required SampleCallback onSample}) {
    _running = true;
    _onSample = onSample;
  }

  @override
  void stop() {
    _running = false;
    _onSample = null;
  }

  void emit(SampleFrame frame) {
    _onSample?.call(frame);
  }
}

class _FakeSocket implements NodeSocket {
  final StreamController<dynamic> _controller = StreamController<dynamic>();
  final List<dynamic> sent = <dynamic>[];

  @override
  Stream<dynamic> get stream => _controller.stream;

  @override
  void send(dynamic data) {
    sent.add(data);
  }

  @override
  Future<void> close() async {
    await _controller.close();
  }

  Future<void> serverSend(dynamic data) async {
    _controller.add(data);
    await Future<void>.delayed(Duration.zero);
  }

  Future<void> serverClose() async {
    await _controller.close();
  }
}

class _FakeSocketClient implements NodeSocketClient {
  final List<_FakeSocket> sockets;
  int _index = 0;

  _FakeSocketClient(this.sockets);

  @override
  NodeSocket connect(Uri uri) {
    if (_index >= sockets.length) {
      throw StateError('no more fake sockets');
    }
    return sockets[_index++];
  }
}

class _InMemoryStore implements LocalStorePort {
  final List<PendingSample> _samples = <PendingSample>[];
  String? recoveredSessionId;
  int _autoId = 1;

  List<int> debugSeqs({required String sessionId, required String deviceId}) {
    final seqs = _samples.where((s) => s.sessionId == sessionId && s.deviceId == deviceId).map((s) => s.seq).toList();
    seqs.sort();
    return seqs;
  }

  @override
  Future<void> clearAllInflight({required String sessionId, required String deviceId}) async {
    for (final sample in _samples) {
      if (sample.sessionId == sessionId && sample.deviceId == deviceId) {}
    }
  }

  @override
  Future<List<PendingSample>> fetchPendingSamples({required String sessionId, required String deviceId, int limit = 250}) async {
    return _samples.where((s) => s.sessionId == sessionId && s.deviceId == deviceId).take(limit).toList();
  }

  @override
  Future<int> getLastSeq(String sessionId, String deviceId) async {
    final list = _samples.where((s) => s.sessionId == sessionId && s.deviceId == deviceId).toList();
    if (list.isEmpty) return 0;
    list.sort((a, b) => a.seq.compareTo(b.seq));
    return list.last.seq;
  }

  @override
  Future<void> insertSample({required String sessionId, required String deviceId, required String deviceRole, required int seq, required SampleFrame frame}) async {
    _samples.add(
      PendingSample(
        id: _autoId++,
        sessionId: sessionId,
        deviceId: deviceId,
        deviceRole: deviceRole,
        seq: seq,
        timestampDeviceUnixNs: frame.timestampDeviceUnixNs,
        elapsedMs: frame.elapsedMs,
        accXG: frame.accXG,
        accYG: frame.accYG,
        accZG: frame.accZG,
        gyroXDeg: frame.gyroXDeg,
        gyroYDeg: frame.gyroYDeg,
        gyroZDeg: frame.gyroZDeg,
      ),
    );
  }

  @override
  Future<void> insertUploadBatch({required String sessionId, required String deviceId, required int startSeq, required int endSeq, required int sampleCount, required String status, String? lastError}) async {}

  @override
  Future<String?> latestUnfinishedSessionId() async => recoveredSessionId;

  @override
  Future<void> markInflightRange({required String sessionId, required String deviceId, required int startSeq, required int endSeq}) async {}

  @override
  Future<void> markUploadedThroughSeq({required String sessionId, required String deviceId, required int lastReceivedSeq}) async {
    _samples.removeWhere((s) => s.sessionId == sessionId && s.deviceId == deviceId && s.seq <= lastReceivedSeq);
  }

  @override
  Future<int> pendingCount({required String sessionId, required String deviceId}) async {
    return _samples.where((s) => s.sessionId == sessionId && s.deviceId == deviceId).length;
  }

  @override
  Future<void> resetUploadFlagsAfterSeq({required String sessionId, required String deviceId, required int backendLastSeq}) async {}

  @override
  Future<int> totalSampleCount({required String sessionId, required String deviceId}) async {
    return pendingCount(sessionId: sessionId, deviceId: deviceId);
  }

  @override
  Future<void> updateSessionStartMarkers({required String sessionId, int? serverStartUnixNs, int? monotonicStartMs}) async {}

  @override
  Future<void> updateSessionStatus(String sessionId, String status, {int? stoppedAtUnixNs}) async {}

  @override
  Future<void> upsertSession({required String sessionId, required String status, int? serverStartUnixNs, int? monotonicStartMs, int? stoppedAtUnixNs}) async {
    recoveredSessionId = sessionId;
  }
}

class _FakeRuntimeGuard implements RuntimeGuardPort {
  bool enabled = false;

  @override
  Future<void> disableRecordingGuard() async {
    enabled = false;
  }

  @override
  Future<void> enableRecordingGuard({required String sessionId, required String deviceId}) async {
    enabled = true;
  }

  @override
  Future<bool> isBatteryOptimizationIgnored() async => true;

  @override
  Future<void> openBatteryOptimizationSettings() async {}
}

void main() {
  test('offline keeps local recording and reconnect replays backlog', () async {
    final config = NodeConfig.defaults().copyWith(
      backendBaseUrl: 'http://127.0.0.1:8000',
      deviceId: 'DEVICE-CHEST-001',
      deviceRole: 'chest',
      sessionId: '20260419_143022_A1B2C3D4',
      wsPort: 8000,
    );

    final store = _InMemoryStore()..recoveredSessionId = config.sessionId;
    final sampler = _FakeSampler();
    final runtimeGuard = _FakeRuntimeGuard();
    final socket1 = _FakeSocket();
    final socket2 = _FakeSocket();
    final controller = DeviceNodeController(
      configStore: _FakeConfigStore(config),
      localStore: store,
      backendClient: _FakeBackendClient(),
      sensorSampler: sampler,
      runtimeGuard: runtimeGuard,
      socketClient: _FakeSocketClient([socket1, socket2]),
      connectivityChanges: () => const Stream<List<ConnectivityResult>>.empty(),
      batteryLevelProvider: () async => 80,
      storageFreeProvider: () async => 1024,
      reconnectDelay: const Duration(milliseconds: 50),
      heartbeatInterval: const Duration(milliseconds: 200),
      uploaderInterval: const Duration(milliseconds: 50),
      statusInterval: const Duration(seconds: 10),
    );

    await controller.initialize();
    await controller.connect();

    final helloRaw = socket1.sent.first as String;
    final hello = jsonDecode(helloRaw) as Map<String, dynamic>;
    expect(hello['type'], 'HELLO');

    await socket1.serverSend(jsonEncode({
      'type': 'HELLO_ACK',
      'session_id': config.sessionId,
      'backend_last_seq': 0,
    }));

    await socket1.serverSend(jsonEncode({
      'type': 'START_SESSION',
      'session_id': config.sessionId,
      'target_sampling_hz': 100,
    }));
    await Future<void>.delayed(const Duration(milliseconds: 5));

    sampler.emit(
      const SampleFrame(
        timestampDeviceUnixNs: 1,
        elapsedMs: 1,
        accXG: 0.1,
        accYG: 0.2,
        accZG: 0.3,
        gyroXDeg: 1,
        gyroYDeg: 2,
        gyroZDeg: 3,
      ),
    );
    expect(await store.pendingCount(sessionId: config.sessionId, deviceId: config.deviceId), 1);

    await socket1.serverClose();
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(controller.state.connected, isFalse);
    expect(controller.state.recording, isTrue);

    sampler.emit(
      const SampleFrame(
        timestampDeviceUnixNs: 2,
        elapsedMs: 2,
        accXG: 0.1,
        accYG: 0.2,
        accZG: 0.3,
        gyroXDeg: 1,
        gyroYDeg: 2,
        gyroZDeg: 3,
      ),
    );
    expect(await store.pendingCount(sessionId: config.sessionId, deviceId: config.deviceId), 2);

    await socket2.serverSend(jsonEncode({
      'type': 'HELLO_ACK',
      'session_id': config.sessionId,
      'backend_last_seq': 0,
    }));
    await Future<void>.delayed(const Duration(milliseconds: 120));

    final reconnectHelloRaw = socket2.sent.firstWhere((m) => m is String) as String;
    final reconnectHello = jsonDecode(reconnectHelloRaw) as Map<String, dynamic>;
    expect(reconnectHello['type'], 'HELLO');
    expect((reconnectHello['local_last_seq'] as num).toInt(), greaterThanOrEqualTo(1));

    final hasBinaryBatch = socket2.sent.any((m) => m is List<int> && m.isNotEmpty);
    expect(hasBinaryBatch, isTrue);

    final bytes = socket2.sent.firstWhere((m) => m is List<int>) as List<int>;
    final batch = SensorBatch.fromBuffer(bytes);
    expect(batch.samples.length, greaterThanOrEqualTo(1));
    expect(batch.endSeq.toInt(), greaterThanOrEqualTo(2));

    await controller.disposeController();
  });

  test('seq tetap monotonic saat sampling berlangsung', () async {
    final config = NodeConfig.defaults().copyWith(
      backendBaseUrl: 'http://127.0.0.1:8000',
      deviceId: 'DEVICE-CHEST-001',
      deviceRole: 'chest',
      sessionId: '20260419_143022_A1B2C3D4',
      wsPort: 8000,
    );

    final store = _InMemoryStore()..recoveredSessionId = config.sessionId;
    final sampler = _FakeSampler();
    final runtimeGuard = _FakeRuntimeGuard();
    final socket = _FakeSocket();
    final controller = DeviceNodeController(
      configStore: _FakeConfigStore(config),
      localStore: store,
      backendClient: _FakeBackendClient(),
      sensorSampler: sampler,
      runtimeGuard: runtimeGuard,
      socketClient: _FakeSocketClient([socket]),
      connectivityChanges: () => const Stream<List<ConnectivityResult>>.empty(),
      batteryLevelProvider: () async => 80,
      storageFreeProvider: () async => 1024,
      reconnectDelay: const Duration(milliseconds: 50),
      heartbeatInterval: const Duration(milliseconds: 200),
      uploaderInterval: const Duration(milliseconds: 200),
      statusInterval: const Duration(seconds: 10),
    );

    await controller.initialize();
    await controller.connect();
    await socket.serverSend(jsonEncode({'type': 'HELLO_ACK', 'session_id': config.sessionId, 'backend_last_seq': 0}));
    await socket.serverSend(jsonEncode({'type': 'START_SESSION', 'session_id': config.sessionId, 'target_sampling_hz': 100}));
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(sampler.isRunning, isTrue);

    sampler.emit(const SampleFrame(timestampDeviceUnixNs: 1, elapsedMs: 1, accXG: 0.1, accYG: 0.2, accZG: 0.3, gyroXDeg: 1, gyroYDeg: 2, gyroZDeg: 3));
    sampler.emit(const SampleFrame(timestampDeviceUnixNs: 2, elapsedMs: 2, accXG: 0.1, accYG: 0.2, accZG: 0.3, gyroXDeg: 1, gyroYDeg: 2, gyroZDeg: 3));
    sampler.emit(const SampleFrame(timestampDeviceUnixNs: 3, elapsedMs: 3, accXG: 0.1, accYG: 0.2, accZG: 0.3, gyroXDeg: 1, gyroYDeg: 2, gyroZDeg: 3));

    await Future<void>.delayed(const Duration(milliseconds: 30));

    final seqs = store.debugSeqs(sessionId: config.sessionId, deviceId: config.deviceId);
    expect(seqs, equals(<int>[1, 2, 3]));
    expect(controller.state.lastSeq, 3);

    await controller.disposeController();
  });

  test('command handling start dan stop menghasilkan stop ack', () async {
    final config = NodeConfig.defaults().copyWith(
      backendBaseUrl: 'http://127.0.0.1:8000',
      deviceId: 'DEVICE-CHEST-001',
      deviceRole: 'chest',
      sessionId: '20260419_143022_A1B2C3D4',
      wsPort: 8000,
    );

    final store = _InMemoryStore()..recoveredSessionId = config.sessionId;
    final sampler = _FakeSampler();
    final runtimeGuard = _FakeRuntimeGuard();
    final socket = _FakeSocket();
    final controller = DeviceNodeController(
      configStore: _FakeConfigStore(config),
      localStore: store,
      backendClient: _FakeBackendClient(),
      sensorSampler: sampler,
      runtimeGuard: runtimeGuard,
      socketClient: _FakeSocketClient([socket]),
      connectivityChanges: () => const Stream<List<ConnectivityResult>>.empty(),
      batteryLevelProvider: () async => 80,
      storageFreeProvider: () async => 1024,
      reconnectDelay: const Duration(milliseconds: 50),
      heartbeatInterval: const Duration(milliseconds: 200),
      uploaderInterval: const Duration(milliseconds: 50),
      statusInterval: const Duration(seconds: 10),
    );

    await controller.initialize();
    await controller.connect();
    await socket.serverSend(jsonEncode({'type': 'HELLO_ACK', 'session_id': config.sessionId, 'backend_last_seq': 0}));

    await socket.serverSend(jsonEncode({'type': 'START_SESSION', 'session_id': config.sessionId, 'target_sampling_hz': 100}));
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(controller.state.recording, isTrue);

    await socket.serverSend(jsonEncode({'type': 'STOP_SESSION', 'session_id': config.sessionId, 'command_id': 'stop-123'}));
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(controller.state.recording, isFalse);

    final stopAckRaw = socket.sent.whereType<String>().map((it) => jsonDecode(it) as Map<String, dynamic>).where((it) => it['type'] == 'STOP_SESSION_ACK').toList();
    expect(stopAckRaw, isNotEmpty);
    expect(stopAckRaw.last['command_id'], 'stop-123');

    await controller.disposeController();
  });
}
