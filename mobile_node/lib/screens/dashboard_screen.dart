import 'dart:async';
import 'package:flutter/material.dart';
import '../services/internal_sensor_manager.dart';
import '../services/websocket_client.dart';
import '../widgets/graph_widget.dart';
import '../models/sensor_packet.dart';
import 'connection_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  StreamSubscription? _stateSub;
  StreamSubscription? _eventSub;
  Stream<SensorPacket>? _sensorStream;

  WsState _wsState = WsState.disconnected;
  bool _isRecording = false;
  int _packetsSent = 0;
  int _packetsBuffered = 0;
  String? _sessionId;
  int _activeLabel = 0;

  @override
  void initState() {
    super.initState();
    InternalSensorManager().start(frequency: 100);
    _sensorStream = InternalSensorManager().dataStream;
    WebSocketClient().attachSensorStream(_sensorStream!);

    _stateSub = WebSocketClient().stateStream.listen((s) {
      setState(() => _wsState = s);
    });

    _eventSub = WebSocketClient().eventStream.listen(_onEvent);

    // Reflect current state immediately.
    _wsState = WebSocketClient().state;
  }

  void _onEvent(Map<String, dynamic> e) {
    final type = e['type'] as String?;
    setState(() {
      _packetsSent = WebSocketClient().packetsSent;
      _packetsBuffered = WebSocketClient().packetsBuffered;
      _sessionId = WebSocketClient().activeSessionId;
      if (type == 'start_session') _isRecording = true;
      if (type == 'stop_session') {
        _isRecording = false;
        _activeLabel = 0;
      }
      if (type == 'set_label') {
        try {
          final payload = e['payload'] as String;
          // payload JSON: {"label_id": N, ...}
          final match = RegExp(r'"label_id"\s*:\s*(\d+)').firstMatch(payload);
          if (match != null) _activeLabel = int.parse(match.group(1)!);
        } catch (_) {}
      }
    });
  }

  @override
  void dispose() {
    _stateSub?.cancel();
    _eventSub?.cancel();
    InternalSensorManager().stop();
    WebSocketClient().detachSensorStream();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: _isRecording ? Colors.red.shade900 : const Color(0xFF16213E),
        title: const Text('IMU Node', style: TextStyle(color: Colors.white)),
        actions: [
          _WsStatusDot(_wsState),
          const SizedBox(width: 12),
        ],
        leading: IconButton(
          icon: const Icon(Icons.logout, color: Colors.white54),
          onPressed: _disconnect,
          tooltip: 'Disconnect',
        ),
      ),
      body: Column(
        children: [
          _StatusBar(
            isRecording: _isRecording,
            sessionId: _sessionId,
            sent: _packetsSent,
            buffered: _packetsBuffered,
            activeLabel: _activeLabel,
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(8),
              children: [
                _sectionLabel('Accelerometer (g)'),
                GraphWidget(
                    size: const Size(double.infinity, 80),
                    maxPoints: 100,
                    dataStream: _sensorStream!,
                    sensorType: 'accel',
                    axis: 'x'),
                GraphWidget(
                    size: const Size(double.infinity, 80),
                    maxPoints: 100,
                    dataStream: _sensorStream!,
                    sensorType: 'accel',
                    axis: 'y'),
                GraphWidget(
                    size: const Size(double.infinity, 80),
                    maxPoints: 100,
                    dataStream: _sensorStream!,
                    sensorType: 'accel',
                    axis: 'z'),
                const SizedBox(height: 8),
                _sectionLabel('Gyroscope (°/s)'),
                GraphWidget(
                    size: const Size(double.infinity, 80),
                    maxPoints: 100,
                    dataStream: _sensorStream!,
                    sensorType: 'gyro',
                    axis: 'x'),
                GraphWidget(
                    size: const Size(double.infinity, 80),
                    maxPoints: 100,
                    dataStream: _sensorStream!,
                    sensorType: 'gyro',
                    axis: 'y'),
                GraphWidget(
                    size: const Size(double.infinity, 80),
                    maxPoints: 100,
                    dataStream: _sensorStream!,
                    sensorType: 'gyro',
                    axis: 'z'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionLabel(String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
        child: Text(text,
            style: const TextStyle(
                color: Colors.white54,
                fontSize: 12,
                fontWeight: FontWeight.bold)),
      );

  Future<void> _disconnect() async {
    await WebSocketClient().disconnect();
    if (!mounted) return;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const ConnectionScreen()),
    );
  }
}

class _WsStatusDot extends StatelessWidget {
  final WsState state;
  const _WsStatusDot(this.state);

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (state) {
      WsState.connected => (Colors.greenAccent, 'LIVE'),
      WsState.connecting => (Colors.amber, 'CONNECTING'),
      WsState.offline => (Colors.orange, 'OFFLINE'),
      WsState.disconnected => (Colors.red, 'DISCONNECTED'),
    };
    return Row(
      children: [
        Container(
            width: 8,
            height: 8,
            decoration:
                BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 4),
        Text(label,
            style: TextStyle(
                color: color, fontSize: 11, fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _StatusBar extends StatelessWidget {
  final bool isRecording;
  final String? sessionId;
  final int sent;
  final int buffered;
  final int activeLabel;

  const _StatusBar({
    required this.isRecording,
    required this.sessionId,
    required this.sent,
    required this.buffered,
    required this.activeLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0F3460),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isRecording ? '● RECORDING' : '○ STANDBY',
                style: TextStyle(
                    color: isRecording ? Colors.redAccent : Colors.white38,
                    fontWeight: FontWeight.bold,
                    fontSize: 12),
              ),
              if (sessionId != null)
                Text('Session: ${sessionId!.substring(0, 8)}…',
                    style: const TextStyle(
                        color: Colors.white38, fontSize: 10)),
            ],
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('Sent: $sent',
                  style: const TextStyle(color: Colors.white70, fontSize: 11)),
              if (buffered > 0)
                Text('Buffered: $buffered',
                    style: const TextStyle(
                        color: Colors.orange, fontSize: 11)),
              if (isRecording && activeLabel > 0)
                Text('Label: $activeLabel',
                    style: const TextStyle(
                        color: Colors.greenAccent, fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}
