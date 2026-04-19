import 'dart:async';
import 'dart:convert';

import 'package:battery_plus/battery_plus.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:fixnum/fixnum.dart' as $fixnum;
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../generated/control.pb.dart';
import '../generated/sensor_sample.pb.dart';
import '../models/node_config.dart';
import '../models/pending_sample.dart';
import '../models/sample_frame.dart';
import 'backend_client.dart';
import 'local_store.dart';
import 'node_config_store.dart';
import 'sensor_sampler.dart';
import 'storage_info_service.dart';

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
    );
  }
}

class DeviceNodeController extends ChangeNotifier {
  DeviceNodeController({
    required NodeConfigStore configStore,
    required LocalStore localStore,
    required BackendClient backendClient,
    required SensorSampler sensorSampler,
  })  : _configStore = configStore,
        _localStore = localStore,
        _backendClient = backendClient,
        _sensorSampler = sensorSampler;

  final NodeConfigStore _configStore;
  final LocalStore _localStore;
  final BackendClient _backendClient;
  final SensorSampler _sensorSampler;
  final Battery _battery = Battery();
  final StorageInfoService _storageInfoService = StorageInfoService();

  NodeConfig _config = NodeConfig.defaults();
  DeviceNodeState _state = DeviceNodeState.initial();
  DeviceNodeState get state => _state;
  NodeConfig get config => _config;

  WebSocketChannel? _channel;
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
    _connectivitySub = Connectivity().onConnectivityChanged.listen((_) {
      if (!_manualDisconnect && !_state.connected) {
        _scheduleReconnect('network change');
      }
    });
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
    if (_config.sessionId.isEmpty) {
      _setInfo('session_id wajib diisi sebelum connect');
      return;
    }

    try {
      await _backendClient.registerDevice(_config);
      _channel = IOWebSocketChannel.connect(_buildWsUri());
      _wsSub = _channel!.stream.listen(
        _onWsMessage,
        onDone: _onWsDone,
        onError: (Object error) {
          _setInfo('ws error: $error');
          _onWsDone();
        },
      );

      final lastSeq = await _localStore.getLastSeq(_config.sessionId, _config.deviceId);
      _seq = lastSeq;
      _sendJson({
        'type': 'HELLO',
        'device_id': _config.deviceId,
        'device_role': _config.deviceRole,
        'session_id': _config.sessionId,
        'local_last_seq': lastSeq,
      });

      _state = _state.copyWith(lastInfo: 'hello sent', sessionId: _config.sessionId, lastSeq: _seq);
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

    await _wsSub?.cancel();
    _wsSub = null;

    await _channel?.sink.close();
    _channel = null;

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
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      _sendJson({'type': 'HEARTBEAT'});
    });

    _uploaderTimer?.cancel();
    _uploaderTimer = Timer.periodic(const Duration(milliseconds: 500), (_) {
      unawaited(_uploadPendingBatches());
    });

    _statusPushTimer?.cancel();
    _statusPushTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      unawaited(_pushDeviceStatus());
    });
  }

  void _onWsDone() {
    if (_state.connected) {
      _state = _state.copyWith(connected: false, recording: false, lastInfo: 'ws disconnected');
      notifyListeners();
    }
    if (!_manualDisconnect) {
      _scheduleReconnect('socket done');
    }
  }

  void _scheduleReconnect(String reason) {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
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
          _sendClockSyncPong(commandId: command.commandId);
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
      _state = _state.copyWith(
        connected: true,
        sessionId: (payload['session_id'] as String? ?? _state.sessionId),
        lastInfo: 'connected',
      );
      notifyListeners();
      unawaited(_localStore.clearAllInflight(
        sessionId: _state.sessionId,
        deviceId: _config.deviceId,
      ));
      unawaited(_localStore.resetUploadFlagsAfterSeq(
        sessionId: _state.sessionId,
        deviceId: _config.deviceId,
        backendLastSeq: backendLastSeq,
      ));
      return;
    }

    if (type == 'ACK') {
      final lastReceivedSeq = (payload['last_received_seq'] as num? ?? 0).toInt();
      unawaited(_onAck(lastReceivedSeq));
      return;
    }

    if (type == 'CLOCK_SYNC_PING') {
      _sendClockSyncPong(pingId: payload['ping_id'] as String? ?? '');
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
      frequencyHz: command.hasTargetSamplingHz() && command.targetSamplingHz > 0 ? command.targetSamplingHz : 100,
      logicalStartUnixNs: targetStartNs,
      onSample: (frame) {
        _onSample(sessionId, frame);
      },
    );

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

  void _sendClockSyncPong({String? pingId, String? commandId}) {
    final usedPingId = pingId ?? commandId ?? '';
    if (usedPingId.isEmpty) {
      return;
    }
    _sendJson({
      'type': 'CLOCK_SYNC_PONG',
      'session_id': _state.sessionId,
      'device_id': _config.deviceId,
      'ping_id': usedPingId,
      'device_unix_ns': DateTime.now().microsecondsSinceEpoch * 1000,
    });
  }

  Future<void> _onSample(String sessionId, SampleFrame frame) async {
    _seq += 1;
    _sampleWindowCount += 1;

    if (_sampleWindow.elapsedMilliseconds >= 1000) {
      final hz = _sampleWindowCount / (_sampleWindow.elapsedMilliseconds / 1000);
      _state = _state.copyWith(effectiveHz: hz, lastSeq: _seq);
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
      _channel?.sink.add(batch.writeToBuffer());
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
      final battery = await _battery.batteryLevel;
      final storageFreeMb = await _storageInfoService.getFreeStorageMb();
      await _backendClient.patchDeviceStatus(
        config: _config,
        connected: _state.connected,
        recording: _state.recording,
        batteryPercent: battery.toDouble(),
        storageFreeMb: storageFreeMb,
        effectiveHz: _state.effectiveHz,
      );
      _state = _state.copyWith(batteryPercent: battery, storageFreeMb: storageFreeMb);
      notifyListeners();
    } catch (e) {
      _setInfo('status push failed: $e');
    }
  }

  void _sendJson(Map<String, dynamic> payload) {
    try {
      _channel?.sink.add(jsonEncode(payload));
    } catch (e) {
      _setInfo('send failed: $e');
    }
  }

  void _setInfo(String info) {
    _state = _state.copyWith(lastInfo: info);
    notifyListeners();
  }
}
