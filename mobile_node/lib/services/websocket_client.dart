import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:uuid/uuid.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/sensor_packet.dart';
import '../models/proto/sensor_packet.pb.dart';
import '../models/proto/commands.pb.dart';
import 'clock_sync_service.dart';
import 'device_id_service.dart';
import 'fallback_buffer_manager.dart';
import 'session_persistence.dart';
import 'foreground_service_handler.dart';

enum WsState { disconnected, connecting, connected, offline }

// Manages telemetry + control WebSocket channels (CLAUDE.md §8).
class WebSocketClient {
  static final WebSocketClient _instance = WebSocketClient._internal();
  factory WebSocketClient() => _instance;
  WebSocketClient._internal();

  WebSocketChannel? _telemetry;
  WebSocketChannel? _control;
  StreamSubscription? _controlSub;
  StreamSubscription? _sensorSub;
  Timer? _pingTimer;
  Timer? _resyncTimer;

  WsState _state = WsState.disconnected;
  WsState get state => _state;
  bool get isConnected => _state == WsState.connected;

  String _serverIp = '';
  String _deviceId = '';
  String _deviceRole = 'chest';
  int _sequence = 0;
  int _packetsSent = 0;
  int _packetsBuffered = 0;
  DateTime? _lastPong;
  String? _activeSessionId;

  // Pending CLOCK_SYNC requests: commandId → t0Ms
  final Map<String, int> _pendingSyncs = {};
  final List<int> _syncOffsets = [];

  // Listeners for UI state updates.
  final _stateController = StreamController<WsState>.broadcast();
  final _eventController = StreamController<Map<String, dynamic>>.broadcast();

  Stream<WsState> get stateStream => _stateController.stream;
  Stream<Map<String, dynamic>> get eventStream => _eventController.stream;

  int get packetsSent => _packetsSent;
  int get packetsBuffered => _packetsBuffered;
  String? get activeSessionId => _activeSessionId;

  // ── Connect ──────────────────────────────────────────────────────────────

  Future<bool> connect(String serverIp) async {
    if (_state == WsState.connecting || _state == WsState.connected) {
      return true;
    }
    _serverIp = serverIp;
    _setState(WsState.connecting);

    _deviceId = await DeviceIdService().getDeviceId();
    _deviceRole = await DeviceIdService().getDeviceRole();
    await DeviceIdService().saveServerIp(serverIp);

    try {
      _control = WebSocketChannel.connect(
        Uri.parse('ws://$serverIp:8000/ws/control'),
      );
      _controlSub = _control!.stream.listen(
        (raw) => _handleControlMessage(raw),
        onDone: _onControlDisconnect,
        onError: (_) => _onControlDisconnect(),
      );

      // Send DeviceRegister on control channel.
      await _sendDeviceRegister();

      _telemetry = WebSocketChannel.connect(
        Uri.parse('ws://$serverIp:8000/ws/telemetry'),
      );
      // Detect server-side drops on the telemetry channel. Without this listener
      // Flutter silently writes to a dead sink — the dashboard chart freezes
      // permanently because _latest_samples on the backend stops updating.
      // Triggering _onControlDisconnect activates the existing reconnect path,
      // which re-opens both channels and flushes any buffered blackbox data.
      _telemetry!.stream.listen(
        null,
        onDone: () { if (_state == WsState.connected) _onControlDisconnect(); },
        onError: (_) { if (_state == WsState.connected) _onControlDisconnect(); },
        cancelOnError: true,
      );

      _setState(WsState.connected);
      _startPingTimer();
      _startClockSync();
      // Start foreground service to keep process alive when screen is off.
      // Guard inside start() means repeated calls on reconnect are safe.
      await ForegroundServiceHandler().start();
      return true;
    } catch (e) {
      _setState(WsState.disconnected);
      return false;
    }
  }

  // ── Attach sensor stream ─────────────────────────────────────────────────

  void attachSensorStream(Stream<SensorPacket> stream) {
    _sensorSub?.cancel();
    _sensorSub = stream.listen(_onSensorPacket);
  }

  void detachSensorStream() {
    _sensorSub?.cancel();
    _sensorSub = null;
  }

  // ── Sensor packet handling ───────────────────────────────────────────────

  void _onSensorPacket(SensorPacket raw) {
    final rawNow = DateTime.now().millisecondsSinceEpoch;
    final correctedNow = ClockSyncService().nowMs;
    final seq = _sequence++;

    final proto = SensorPacketProto(
      accX: raw.accX,
      accY: raw.accY,
      accZ: raw.accZ,
      gyroX: raw.gyroX,
      gyroY: raw.gyroY,
      gyroZ: raw.gyroZ,
      timestampMs: correctedNow,
      rawTimestampMs: rawNow,
      sequenceNumber: seq,
      deviceId: _deviceId,
      schemaVersion: 1,
    );

    final bytes = proto.toBytes();

    if (_state == WsState.connected && _telemetry != null) {
      _telemetry!.sink.add(bytes);
      _packetsSent++;

      // Persist sequence number every 500 packets.
      if (_activeSessionId != null && seq % 500 == 0) {
        _persistSequence(seq);
      }
    } else {
      // Network offline — buffer to disk.
      if (!FallbackBufferManager().isActive) {
        FallbackBufferManager().activate();
      }
      FallbackBufferManager().write(bytes);
      _packetsBuffered = FallbackBufferManager().bufferedCount;
      ForegroundServiceHandler().updateNotification(
        _packetsSent,
        _packetsBuffered,
      );
    }
  }

  // ── Control channel ──────────────────────────────────────────────────────

  Future<void> _handleControlMessage(dynamic raw) async {
    Uint8List bytes;
    if (raw is List<int>) {
      bytes = Uint8List.fromList(raw);
    } else if (raw is Uint8List) {
      bytes = raw;
    } else {
      return;
    }

    final cmd = CommandProto.fromBytes(bytes);
    switch (cmd.type) {
      case CommandType.PONG:
        _lastPong = DateTime.now();
        _emitEvent({'type': 'pong'});

      case CommandType.CLOCK_SYNC:
        final t3Ms = DateTime.now().millisecondsSinceEpoch;
        final t0Ms = _pendingSyncs.remove(cmd.commandId);
        if (t0Ms == null) return;
        final parsed = ClockSyncService.parsePayload(cmd.payload);
        if (parsed == null) return;
        final offset = ClockSyncService().processResponse(
          t0Ms: t0Ms,
          t1Ms: parsed['t1_ms']!,
          t2Ms: parsed['t2_ms']!,
          t3Ms: t3Ms,
        );
        if (offset != null) {
          _syncOffsets.add(offset);
          if (_syncOffsets.length >= 5) {
            ClockSyncService().applyOffsets(_syncOffsets);
            _syncOffsets.clear();
            _emitEvent({
              'type': 'clock_synced',
              'offset_ms': ClockSyncService().clockOffsetMs,
              'rtt_ms': ClockSyncService().lastRttMs,
            });
          }
        }

      case CommandType.START_SESSION:
        try {
          final payload = jsonDecode(cmd.payload) as Map<String, dynamic>;
          _activeSessionId = payload['session_id']?.toString();
          _sequence = 0;   // Reset sequence counter for new session

          // Coordinated start: wait until scheduled_start_ms (CLAUDE.md §22.5)
          final scheduledStartMs = payload['scheduled_start_ms'] as int?;
          if (scheduledStartMs != null) {
            final nowMs = ClockSyncService().nowMs;
            final delayMs = scheduledStartMs - nowMs;
            if (delayMs > 0) {
              await Future.delayed(Duration(milliseconds: delayMs));
            }
          }
        } catch (_) {}
        _emitEvent({'type': 'start_session', 'payload': cmd.payload});
        ForegroundServiceHandler().updateNotification(_packetsSent, 0);

      case CommandType.STOP_SESSION:
        _activeSessionId = null;
        _emitEvent({'type': 'stop_session'});
        SessionPersistence().clear();

      case CommandType.SET_LABEL:
        _emitEvent({'type': 'set_label', 'payload': cmd.payload});

      case CommandType.ACK:
        _emitEvent({'type': 'ack', 'command_id': cmd.commandId});

      case CommandType.ERROR_ALERT:
        _emitEvent({'type': 'error_alert', 'payload': cmd.payload});
    }
  }

  void _onControlDisconnect() {
    if (_state == WsState.disconnected) return;
    _setState(WsState.offline);
    _pingTimer?.cancel();
    _resyncTimer?.cancel();
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    Future.delayed(const Duration(seconds: 3), () async {
      if (_state != WsState.offline) return;
      final ok = await connect(_serverIp);
      if (ok && FallbackBufferManager().isActive) {
        await _flushFallbackBuffer();
      }
    });
  }

  Future<void> _flushFallbackBuffer() async {
    if (!FallbackBufferManager().isActive) return;
    // Send each buffered packet in order, live packets queue in memory meanwhile.
    await for (final bytes in FallbackBufferManager().flushStream()) {
      if (_state != WsState.connected) break;
      _telemetry?.sink.add(bytes);
    }
    await FallbackBufferManager().clearAfterFlush();
    _packetsBuffered = 0;
  }

  // ── Commands ─────────────────────────────────────────────────────────────

  Future<void> sendCommand(CommandProto cmd) async {
    if (_state != WsState.connected) return;
    _control?.sink.add(cmd.toBytes());
  }

  Future<void> _sendDeviceRegister() async {
    final proto = DeviceRegisterProto(
      deviceId: _deviceId,
      deviceRole: _deviceRole,
      deviceModel: 'Android',
      androidVersion: '',
      appVersion: '2.0.0',
      schemaVersion: 1,
    );
    _control?.sink.add(proto.toBytes());
  }

  // Seconds without a PONG before declaring the control channel offline.
  // 8 s tolerates brief Wi-Fi degradation during subject motion (falls, rapid
  // walking) without triggering a spurious reconnect cycle. A genuine dropout
  // (phone dead, strap removed) is still detected within this window so the
  // backend integrity report can flag the exact offline interval.
  static const int _pongTimeoutSec = 8;

  void _startPingTimer() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      sendCommand(CommandProto(
        type: CommandType.PING,
        issuedAtMs: DateTime.now().millisecondsSinceEpoch,
      ));
      if (_lastPong != null &&
          DateTime.now().difference(_lastPong!).inSeconds > _pongTimeoutSec) {
        _onControlDisconnect();
      }
    });
  }

  void _startClockSync() {
    _syncOffsets.clear();
    // Send 5 syncs with 200ms gap, then repeat every 5 minutes.
    _doSyncBurst();
    _resyncTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      _syncOffsets.clear();
      _doSyncBurst();
    });
  }

  void _doSyncBurst() {
    for (int i = 0; i < 5; i++) {
      Future.delayed(Duration(milliseconds: i * 200), () {
        if (_state != WsState.connected) return;
        final t0Ms = DateTime.now().millisecondsSinceEpoch;
        final id = const Uuid().v4();
        _pendingSyncs[id] = t0Ms;
        sendCommand(CommandProto(
          type: CommandType.CLOCK_SYNC,
          payload: ClockSyncService.buildPayload(t0Ms),
          issuedAtMs: t0Ms,
          commandId: id,
        ));
      });
    }
  }

  Future<void> _persistSequence(int seq) async {
    if (_activeSessionId == null) return;
    await SessionPersistence().save(
      sessionId: _activeSessionId!,
      deviceId: _deviceId,
      serverIp: _serverIp,
      clockOffsetMs: ClockSyncService().clockOffsetMs,
      lastSequenceNumber: seq,
      deviceRole: _deviceRole,
    );
  }

  // ── Disconnect ───────────────────────────────────────────────────────────

  Future<void> disconnect() async {
    _pingTimer?.cancel();
    _resyncTimer?.cancel();
    _sensorSub?.cancel();
    _controlSub?.cancel();
    await _control?.sink.close();
    await _telemetry?.sink.close();
    _setState(WsState.disconnected);
    await FallbackBufferManager().deactivate();
    // Stop foreground service only on explicit disconnect, not on temporary drops.
    await ForegroundServiceHandler().stop();
  }

  void _setState(WsState s) {
    _state = s;
    _stateController.add(s);
  }

  void _emitEvent(Map<String, dynamic> e) => _eventController.add(e);
}
