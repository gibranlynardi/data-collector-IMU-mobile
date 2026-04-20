import 'dart:async';
import 'dart:convert';

import 'package:battery_plus/battery_plus.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:fixnum/fixnum.dart' as $fixnum;
import 'package:flutter/foundation.dart';

import '../generated/control.pb.dart';
import '../generated/sensor_sample.pb.dart';
import '../models/node_config.dart';
import '../models/pending_sample.dart';
import '../models/sample_frame.dart';
import 'backend_client.dart';
import 'local_store.dart';
import 'node_config_store.dart';
import 'sensor_sampler.dart';
import 'socket_client.dart';
import 'storage_info_service.dart';
import 'runtime_guard_service.dart';

class DeviceNodeState {
  const DeviceNodeState({
    required this.connected,
    required this.recording,
    required this.sessionId,
    required this.pendingSamples,
    required this.localSamples,
    required this.lastInfo,
    required this.effectiveHz,
    required this.batteryPercent,
    required this.storageFreeMb,
    required this.lastSeq,
    required this.intervalP99Ms,
    required this.jitterP99Ms,
    required this.foregroundGuardActive,
    required this.batteryOptimizationIgnored,
  });

  final bool connected;
  final bool recording;
  final String sessionId;
  final int pendingSamples;
  final int localSamples;
  final String lastInfo;
  final double effectiveHz;
  final int? batteryPercent;
  final int? storageFreeMb;
  final int lastSeq;
  final double intervalP99Ms;
  final double jitterP99Ms;
  final bool foregroundGuardActive;
  final bool batteryOptimizationIgnored;

  DeviceNodeState copyWith({
    bool? connected,
    bool? recording,
    String? sessionId,
    int? pendingSamples,
    int? localSamples,
    String? lastInfo,
    double? effectiveHz,
    int? batteryPercent,
    int? storageFreeMb,
    int? lastSeq,
    double? intervalP99Ms,
    double? jitterP99Ms,
    bool? foregroundGuardActive,
    bool? batteryOptimizationIgnored,
  }) {
    return DeviceNodeState(
      connected: connected ?? this.connected,
      recording: recording ?? this.recording,
      sessionId: sessionId ?? this.sessionId,
      pendingSamples: pendingSamples ?? this.pendingSamples,
      localSamples: localSamples ?? this.localSamples,
      lastInfo: lastInfo ?? this.lastInfo,
      effectiveHz: effectiveHz ?? this.effectiveHz,
      batteryPercent: batteryPercent ?? this.batteryPercent,
      storageFreeMb: storageFreeMb ?? this.storageFreeMb,
      lastSeq: lastSeq ?? this.lastSeq,
      intervalP99Ms: intervalP99Ms ?? this.intervalP99Ms,
      jitterP99Ms: jitterP99Ms ?? this.jitterP99Ms,
      foregroundGuardActive: foregroundGuardActive ?? this.foregroundGuardActive,
      batteryOptimizationIgnored: batteryOptimizationIgnored ?? this.batteryOptimizationIgnored,
    );
  }

  static DeviceNodeState initial() {
    return const DeviceNodeState(
      connected: false,
      recording: false,
      sessionId: '',
      pendingSamples: 0,
      localSamples: 0,
      lastInfo: 'idle',
      effectiveHz: 0,
      batteryPercent: null,
      storageFreeMb: null,
      lastSeq: 0,
      intervalP99Ms: 0,
      jitterP99Ms: 0,
      foregroundGuardActive: false,
      batteryOptimizationIgnored: true,
    );
  }
}

class DeviceNodeController extends ChangeNotifier {
  DeviceNodeController({
    required NodeConfigStore configStore,
    required LocalStorePort localStore,
    required BackendClientPort backendClient,
    required SensorSamplerPort sensorSampler,
    NodeSocketClient? socketClient,
    Stream<List<ConnectivityResult>> Function()? connectivityChanges,
    Future<int> Function()? batteryLevelProvider,
    Future<int?> Function()? storageFreeProvider,
    RuntimeGuardPort? runtimeGuard,
    Duration reconnectDelay = const Duration(seconds: 3),
    Duration heartbeatInterval = const Duration(seconds: 2),
    Duration uploaderInterval = const Duration(milliseconds: 500),
    Duration statusInterval = const Duration(seconds: 5),
  })  : _configStore = configStore,
        _localStore = localStore,
        _backendClient = backendClient,
        _sensorSampler = sensorSampler,
        _socketClient = socketClient ?? IoNodeSocketClient(),
        _connectivityChanges = connectivityChanges ?? (() => Connectivity().onConnectivityChanged),
        _batteryLevelProvider = batteryLevelProvider ?? (() => Battery().batteryLevel),
        _storageFreeProvider = storageFreeProvider ?? (() => StorageInfoService().getFreeStorageMb()),
        _runtimeGuard = runtimeGuard ?? RuntimeGuardService(),
        _reconnectDelay = reconnectDelay,
        _heartbeatInterval = heartbeatInterval,
        _uploaderInterval = uploaderInterval,
        _statusInterval = statusInterval;

  final NodeConfigStore _configStore;
  final LocalStorePort _localStore;
  final BackendClientPort _backendClient;
  final SensorSamplerPort _sensorSampler;
  final NodeSocketClient _socketClient;
  final Stream<List<ConnectivityResult>> Function() _connectivityChanges;
  final Future<int> Function() _batteryLevelProvider;
  final Future<int?> Function() _storageFreeProvider;
  final RuntimeGuardPort _runtimeGuard;
  final Duration _reconnectDelay;
  final Duration _heartbeatInterval;
  final Duration _uploaderInterval;
  final Duration _statusInterval;

  NodeConfig _config = NodeConfig.defaults();
  DeviceNodeState _state = DeviceNodeState.initial();
  DeviceNodeState get state => _state;
  NodeConfig get config => _config;

  NodeSocket? _socket;
  StreamSubscription? _wsSub;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  Timer? _heartbeatTimer;
  Timer? _uploaderTimer;
  Timer? _statusPushTimer;
  Timer? _reconnectTimer;
  Timer? _startBarrierTimer;

  bool _manualDisconnect = false;
  bool _uploadInProgress = false;
  int _seq = 0;
  int _sampleWindowCount = 0;
  final Stopwatch _sampleWindow = Stopwatch()..start();
  final Stopwatch _appMonotonic = Stopwatch()..start();
  final List<double> _intervalWindowMs = <double>[];
  int _targetSamplingHz = 100;
  int? _lastSampleTimestampNs;
  String? _pendingStopCommandId;
  String? _pendingStopSessionId;
  bool _drainingBeforeStopAck = false;

  Future<void> initialize() async {
    _config = await _configStore.load();
    final recoveredSessionId = await _localStore.latestUnfinishedSessionId();
    final activeSessionId = recoveredSessionId ?? _config.sessionId;
    int pending = 0;
    int total = 0;
    int lastSeq = 0;
    if (activeSessionId.isNotEmpty) {
      pending = await _localStore.pendingCount(sessionId: activeSessionId, deviceId: _config.deviceId);
      total = await _localStore.totalSampleCount(sessionId: activeSessionId, deviceId: _config.deviceId);
      lastSeq = await _localStore.getLastSeq(activeSessionId, _config.deviceId);
    }

    _state = _state.copyWith(
      sessionId: activeSessionId,
      pendingSamples: pending,
      localSamples: total,
      lastSeq: lastSeq,
      lastInfo: recoveredSessionId == null ? 'config loaded' : 'recovered local session $recoveredSessionId',
    );
    _connectivitySub = _connectivityChanges().listen((_) {
      if (!_manualDisconnect && !_state.connected) {
        _scheduleReconnect('network change');
      }
    });

    final batteryOptimizationIgnored = await _runtimeGuard.isBatteryOptimizationIgnored();
    _state = _state.copyWith(
      batteryOptimizationIgnored: batteryOptimizationIgnored,
      lastInfo: batteryOptimizationIgnored
          ? _state.lastInfo
          : 'battery optimization aktif, nonaktifkan untuk stabilitas 100 Hz',
    );
    notifyListeners();
  }

  Future<void> saveConfig(NodeConfig config) async {
    _config = config;
    _state = _state.copyWith(sessionId: config.sessionId, lastInfo: 'config updated');
    await _configStore.save(config);
    notifyListeners();
  }

  Uri _buildWsUri() {
    final base = Uri.parse(_config.backendBaseUrl);
    final scheme = base.scheme == 'https' ? 'wss' : 'ws';
    return Uri(
      scheme: scheme,
      host: base.host,
      port: _config.wsPort,
      path: '/ws/device/${_config.deviceId}',
    );
  }

  Future<void> connect() async {
    _manualDisconnect = false;
    if (_state.connected) {
      return;
    }
    try {
      await _backendClient.registerDevice(_config);
      _socket = _socketClient.connect(_buildWsUri());
      _wsSub = _socket!.stream.listen(
        _onWsMessage,
        onDone: _onWsDone,
        onError: (Object error) {
          _setInfo('ws error: $error');
          _onWsDone();
        },
      );

      final helloSessionId = _config.sessionId.trim();
      final lastSeq = helloSessionId.isEmpty ? 0 : await _localStore.getLastSeq(helloSessionId, _config.deviceId);
      _seq = lastSeq;
      _sendJson({
        'type': 'HELLO',
        'device_id': _config.deviceId,
        'device_role': _config.deviceRole,
        'session_id': helloSessionId,
        'local_last_seq': lastSeq,
        'enrollment_token': _config.enrollmentToken,
      });

      _state = _state.copyWith(lastInfo: 'hello sent', sessionId: helloSessionId, lastSeq: _seq);
      notifyListeners();

      _startTimers();
    } catch (e) {
      _setInfo('connect failed: $e');
      _scheduleReconnect('connect fail');
    }
  }

  Future<void> disconnect({bool manual = true}) async {
    _manualDisconnect = manual;
    _heartbeatTimer?.cancel();
    _uploaderTimer?.cancel();
    _statusPushTimer?.cancel();
    _reconnectTimer?.cancel();
    _startBarrierTimer?.cancel();
    await _runtimeGuard.disableRecordingGuard();

    await _wsSub?.cancel();
    _wsSub = null;

    await _socket?.close();
    _socket = null;

    _state = _state.copyWith(connected: false, lastInfo: manual ? 'disconnected' : 'connection closed');
    notifyListeners();

    await _pushDeviceStatus();
  }

  Future<void> disposeController() async {
    await disconnect();
    await _connectivitySub?.cancel();
    _backendClient.close();
  }

  void _startTimers() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      _sendJson({'type': 'HEARTBEAT'});
    });

    _uploaderTimer?.cancel();
    _uploaderTimer = Timer.periodic(_uploaderInterval, (_) {
      unawaited(_uploadPendingBatches());
    });

    _statusPushTimer?.cancel();
    _statusPushTimer = Timer.periodic(_statusInterval, (_) {
      unawaited(_pushDeviceStatus());
    });
  }

  void _onWsDone() {
    if (_state.connected) {
      _state = _state.copyWith(connected: false, recording: _sensorSampler.isRunning, lastInfo: 'ws disconnected');
      notifyListeners();
    }
    if (!_manualDisconnect) {
      _scheduleReconnect('socket done');
    }
  }

  void _scheduleReconnect(String reason) {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(_reconnectDelay, () {
      _setInfo('reconnect: $reason');
      unawaited(connect());
    });
  }

  void _onWsMessage(dynamic message) {
    if (message is List<int>) {
      _handleBinaryMessage(message);
      return;
    }
    if (message is String) {
      _handleTextMessage(message);
    }
  }

  void _handleBinaryMessage(List<int> payload) {
    try {
      final command = ControlCommand.fromBuffer(payload);
      switch (command.command) {
        case ControlCommandType.START_SESSION:
          unawaited(_handleStartCommand(command));
          break;
        case ControlCommandType.STOP_SESSION:
          unawaited(_handleStopCommand(command));
          break;
        case ControlCommandType.SYNC_CLOCK:
          _sendClockSyncPong(commandId: command.commandId, sessionId: command.sessionId);
          break;
        case ControlCommandType.SYNC_REQUIRED:
          _setInfo('sync required received');
          unawaited(_uploadPendingBatches());
          break;
        case ControlCommandType.PING:
          _sendJson({'type': 'HEARTBEAT'});
          break;
        default:
          _setInfo('binary control ignored: ${command.command.name}');
      }
    } catch (e) {
      _setInfo('invalid binary payload: $e');
    }
  }

  void _handleTextMessage(String text) {
    final payload = jsonDecode(text);
    if (payload is! Map<String, dynamic>) {
      return;
    }

    final type = payload['type'] as String? ?? '';
    if (type == 'HELLO_ACK') {
      final backendLastSeq = (payload['backend_last_seq'] as num? ?? 0).toInt();
      final ackSessionId = (payload['session_id'] as String? ?? '').trim();
      _state = _state.copyWith(
        connected: true,
        sessionId: ackSessionId.isEmpty ? _state.sessionId : ackSessionId,
        lastInfo: 'connected',
      );
      notifyListeners();
      if (_state.sessionId.isNotEmpty) {
        unawaited(_localStore.clearAllInflight(
          sessionId: _state.sessionId,
          deviceId: _config.deviceId,
        ));
        unawaited(_localStore.resetUploadFlagsAfterSeq(
          sessionId: _state.sessionId,
          deviceId: _config.deviceId,
          backendLastSeq: backendLastSeq,
        ));
      }
      return;
    }

    if (type == 'ACK') {
      final lastReceivedSeq = (payload['last_received_seq'] as num? ?? 0).toInt();
      unawaited(_onAck(lastReceivedSeq));
      return;
    }

    if (type == 'CLOCK_SYNC_PING') {
      _sendClockSyncPong(
        pingId: payload['ping_id'] as String? ?? '',
        sessionId: payload['session_id'] as String? ?? '',
      );
      return;
    }

    if (type == 'START_SESSION') {
      final cmd = ControlCommand()
        ..command = ControlCommandType.START_SESSION
        ..sessionId = (payload['session_id'] as String? ?? _config.sessionId)
        ..targetSamplingHz = (payload['target_sampling_hz'] as num? ?? 100).toInt();
      unawaited(_handleStartCommand(cmd));
      return;
    }

    if (type == 'STOP_SESSION') {
      final cmd = ControlCommand()
        ..command = ControlCommandType.STOP_SESSION
        ..sessionId = (payload['session_id'] as String? ?? _state.sessionId)
        ..commandId = (payload['command_id'] as String? ?? '');
      unawaited(_handleStopCommand(cmd));
      return;
    }

    if (type == 'SYNC_REQUIRED') {
      _setInfo('sync required received');
      unawaited(_uploadPendingBatches());
      return;
    }

    if (type == 'ERROR') {
      _setInfo('server error: ${payload['code']} ${payload['detail']}');
      return;
    }
  }

  Future<void> _handleStartCommand(ControlCommand command) async {
    final sessionId = command.sessionId.isNotEmpty ? command.sessionId : _config.sessionId;
    if (sessionId.isEmpty) {
      _setInfo('start ignored: session_id kosong');
      return;
    }

    if (_state.recording && _state.sessionId == sessionId) {
      return;
    }

    _config = _config.copyWith(sessionId: sessionId);
    await _configStore.save(_config);

    _seq = await _localStore.getLastSeq(sessionId, _config.deviceId);

    await _localStore.upsertSession(
      sessionId: sessionId,
      status: 'running',
      serverStartUnixNs: command.hasServerStartTimeUnixNs() ? command.serverStartTimeUnixNs.toInt() : null,
      monotonicStartMs: null,
    );

    _sampleWindow
      ..reset()
      ..start();
    _sampleWindowCount = 0;
    _intervalWindowMs.clear();
    _lastSampleTimestampNs = null;
    _targetSamplingHz = command.hasTargetSamplingHz() && command.targetSamplingHz > 0 ? command.targetSamplingHz : 100;

    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
    final requestedStartNs = command.hasServerStartTimeUnixNs() ? command.serverStartTimeUnixNs.toInt() : nowNs;
    final targetStartNs = requestedStartNs > nowNs ? requestedStartNs : nowNs;
    final delayMs = ((targetStartNs - nowNs) / 1000000).ceil();
    _startBarrierTimer?.cancel();
    _startBarrierTimer = Timer(Duration(milliseconds: delayMs < 0 ? 0 : delayMs), () {
      _startSamplingWithBarrier(sessionId, command, targetStartNs);
    });

    _state = _state.copyWith(recording: true, sessionId: sessionId, lastInfo: 'start armed (${delayMs < 0 ? 0 : delayMs}ms)');
    notifyListeners();
    await _pushDeviceStatus();
  }

  void _startSamplingWithBarrier(String sessionId, ControlCommand command, int targetStartNs) {
    _sampleWindow
      ..reset()
      ..start();
    _sampleWindowCount = 0;

    _sensorSampler.start(
      frequencyHz: _targetSamplingHz,
      logicalStartUnixNs: targetStartNs,
      onSample: (frame) {
        _onSample(sessionId, frame);
      },
    );

    unawaited(_runtimeGuard.enableRecordingGuard(sessionId: sessionId, deviceId: _config.deviceId));
    _state = _state.copyWith(foregroundGuardActive: true);
    notifyListeners();

    unawaited(_localStore.updateSessionStartMarkers(
      sessionId: sessionId,
      serverStartUnixNs: targetStartNs,
      monotonicStartMs: _appMonotonic.elapsedMilliseconds,
    ));

    _setInfo('recording started (barrier synced)');
  }

  Future<void> _handleStopCommand(ControlCommand command) async {
    final sessionId = command.sessionId.isNotEmpty ? command.sessionId : _state.sessionId;
    _startBarrierTimer?.cancel();
    _sensorSampler.stop();
    await _runtimeGuard.disableRecordingGuard();

    if (sessionId.isNotEmpty) {
      await _localStore.updateSessionStatus(
        sessionId,
        'stopped',
        stoppedAtUnixNs: DateTime.now().microsecondsSinceEpoch * 1000,
      );
    }

    _state = _state.copyWith(recording: false, lastInfo: 'recording stopped; draining queue');
    notifyListeners();

    _pendingStopCommandId = command.commandId;
    _pendingStopSessionId = sessionId;
    _drainingBeforeStopAck = true;
    await _maybeSendStopAck();

    await _pushDeviceStatus();
  }

  void _sendClockSyncPong({String? pingId, String? commandId, String? sessionId}) {
    final usedPingId = pingId ?? commandId ?? '';
    if (usedPingId.isEmpty) {
      return;
    }
    final session = (sessionId != null && sessionId.trim().isNotEmpty) ? sessionId.trim() : _state.sessionId;
    _sendJson({
      'type': 'CLOCK_SYNC_PONG',
      'session_id': session,
      'device_id': _config.deviceId,
      'ping_id': usedPingId,
      'device_unix_ns': DateTime.now().microsecondsSinceEpoch * 1000,
    });
  }

  Future<void> _onSample(String sessionId, SampleFrame frame) async {
    _seq += 1;
    _sampleWindowCount += 1;

    if (_lastSampleTimestampNs != null) {
      final intervalMs = (frame.timestampDeviceUnixNs - _lastSampleTimestampNs!) / 1000000.0;
      if (intervalMs > 0 && intervalMs < 2000) {
        _intervalWindowMs.add(intervalMs);
        if (_intervalWindowMs.length > 256) {
          _intervalWindowMs.removeAt(0);
        }
      }
    }
    _lastSampleTimestampNs = frame.timestampDeviceUnixNs;

    if (_sampleWindow.elapsedMilliseconds >= 1000) {
      final hz = _sampleWindowCount / (_sampleWindow.elapsedMilliseconds / 1000);
      final p99Ms = _computeP99IntervalMs();
      final targetIntervalMs = 1000.0 / (_targetSamplingHz <= 0 ? 100 : _targetSamplingHz);
      final jitterP99Ms = (p99Ms - targetIntervalMs).abs();
      _state = _state.copyWith(
        effectiveHz: hz,
        intervalP99Ms: p99Ms,
        jitterP99Ms: jitterP99Ms,
        lastSeq: _seq,
      );
      notifyListeners();
      _sampleWindow
        ..reset()
        ..start();
      _sampleWindowCount = 0;
    }

    await _localStore.insertSample(
      sessionId: sessionId,
      deviceId: _config.deviceId,
      deviceRole: _config.deviceRole,
      seq: _seq,
      frame: frame,
    );

    final pending = await _localStore.pendingCount(sessionId: sessionId, deviceId: _config.deviceId);
    final total = await _localStore.totalSampleCount(sessionId: sessionId, deviceId: _config.deviceId);
    _state = _state.copyWith(pendingSamples: pending, localSamples: total, lastSeq: _seq);
    notifyListeners();
  }

  double _computeP99IntervalMs() {
    if (_intervalWindowMs.isEmpty) {
      return 0;
    }
    final sorted = List<double>.from(_intervalWindowMs)..sort();
    final rawIndex = (sorted.length * 0.99).ceil() - 1;
    final index = rawIndex < 0
        ? 0
        : (rawIndex >= sorted.length ? sorted.length - 1 : rawIndex);
    return sorted[index];
  }

  Future<void> openBatteryOptimizationSettings() async {
    await _runtimeGuard.openBatteryOptimizationSettings();
  }

  Future<void> _uploadPendingBatches() async {
    if (_uploadInProgress || !_state.connected || _state.sessionId.isEmpty) {
      if (_drainingBeforeStopAck) {
        await _maybeSendStopAck();
      }
      return;
    }
    _uploadInProgress = true;
    try {
      final pending = await _localStore.fetchPendingSamples(
        sessionId: _state.sessionId,
        deviceId: _config.deviceId,
        limit: 250,
      );

      if (pending.isEmpty) {
        return;
      }

      final batch = _toBatch(pending);
      await _localStore.insertUploadBatch(
        sessionId: _state.sessionId,
        deviceId: _config.deviceId,
        startSeq: pending.first.seq,
        endSeq: pending.last.seq,
        sampleCount: pending.length,
        status: 'sent',
      );
      await _localStore.markInflightRange(
        sessionId: _state.sessionId,
        deviceId: _config.deviceId,
        startSeq: pending.first.seq,
        endSeq: pending.last.seq,
      );
      _socket?.send(batch.writeToBuffer());
    } catch (e) {
      if (_state.sessionId.isNotEmpty) {
        await _localStore.clearAllInflight(
          sessionId: _state.sessionId,
          deviceId: _config.deviceId,
        );
      }
      await _localStore.insertUploadBatch(
        sessionId: _state.sessionId,
        deviceId: _config.deviceId,
        startSeq: 0,
        endSeq: 0,
        sampleCount: 0,
        status: 'failed',
        lastError: e.toString(),
      );
      _setInfo('upload error: $e');
    } finally {
      _uploadInProgress = false;
      if (_drainingBeforeStopAck) {
        await _maybeSendStopAck();
      }
    }
  }

  SensorBatch _toBatch(List<PendingSample> pending) {
    final batch = SensorBatch()
      ..sessionId = pending.first.sessionId
      ..deviceId = pending.first.deviceId
      ..startSeq = $fixnum.Int64(pending.first.seq)
      ..endSeq = $fixnum.Int64(pending.last.seq);

    for (final item in pending) {
      final sample = SensorSample()
        ..sessionId = item.sessionId
        ..deviceId = item.deviceId
        ..deviceRole = item.deviceRole
        ..seq = $fixnum.Int64(item.seq)
        ..timestampDeviceUnixNs = $fixnum.Int64(item.timestampDeviceUnixNs)
        ..elapsedMs = $fixnum.Int64(item.elapsedMs)
        ..accXG = item.accXG
        ..accYG = item.accYG
        ..accZG = item.accZG
        ..gyroXDeg = item.gyroXDeg
        ..gyroYDeg = item.gyroYDeg
        ..gyroZDeg = item.gyroZDeg;
      batch.samples.add(sample);
    }
    return batch;
  }

  Future<void> _onAck(int lastReceivedSeq) async {
    if (_state.sessionId.isEmpty || lastReceivedSeq <= 0) {
      return;
    }
    await _localStore.markUploadedThroughSeq(
      sessionId: _state.sessionId,
      deviceId: _config.deviceId,
      lastReceivedSeq: lastReceivedSeq,
    );
    final pending = await _localStore.pendingCount(sessionId: _state.sessionId, deviceId: _config.deviceId);
    final total = await _localStore.totalSampleCount(sessionId: _state.sessionId, deviceId: _config.deviceId);
    _state = _state.copyWith(pendingSamples: pending, localSamples: total, lastInfo: 'ack $lastReceivedSeq');
    notifyListeners();
    if (_drainingBeforeStopAck) {
      await _maybeSendStopAck();
    }
  }

  Future<void> _maybeSendStopAck() async {
    if (!_drainingBeforeStopAck || _pendingStopCommandId == null || _pendingStopSessionId == null) {
      return;
    }
    final pending = await _localStore.pendingCount(sessionId: _pendingStopSessionId!, deviceId: _config.deviceId);
    if (pending > 0) {
      _setInfo('draining before stop ack: $pending pending');
      return;
    }

    _sendJson({
      'type': 'STOP_SESSION_ACK',
      'session_id': _pendingStopSessionId,
      'device_id': _config.deviceId,
      'command_id': _pendingStopCommandId,
      'last_local_seq': _seq,
      'pending_samples': 0,
      'drain_complete': true,
    });
    _drainingBeforeStopAck = false;
    _pendingStopCommandId = null;
    _pendingStopSessionId = null;
    _setInfo('stop ack sent after drain');
  }

  Future<void> _pushDeviceStatus() async {
    try {
      final battery = await _batteryLevelProvider();
      final storageFreeMb = await _storageFreeProvider();
      await _backendClient.patchDeviceStatus(
        config: _config,
        connected: _state.connected,
        recording: _state.recording,
        batteryPercent: battery.toDouble(),
        storageFreeMb: storageFreeMb,
        effectiveHz: _state.effectiveHz,
        intervalP99Ms: _state.intervalP99Ms,
        jitterP99Ms: _state.jitterP99Ms,
      );
      _state = _state.copyWith(batteryPercent: battery, storageFreeMb: storageFreeMb);
      notifyListeners();
    } catch (e) {
      _setInfo('status push failed: $e');
    }
  }

  void _sendJson(Map<String, dynamic> payload) {
    try {
      _socket?.send(jsonEncode(payload));
    } catch (e) {
      _setInfo('send failed: $e');
    }
  }

  void _setInfo(String info) {
    _state = _state.copyWith(lastInfo: info);
    notifyListeners();
  }
}
