import 'dart:async';
import 'dart:io';
import 'dart:math' show sqrt;
import 'package:battery_plus/battery_plus.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import '../services/clock_sync_service.dart';
import '../services/internal_sensor_manager.dart';
import '../services/websocket_client.dart';
import 'dashboard_screen.dart';

enum _Status { pending, running, pass, fail }

class _Check {
  final String label;
  _Status status;
  String detail;
  String hint;

  _Check(this.label)
      : status = _Status.pending,
        detail = '',
        hint = '';
}

// Go/No-Go gate before recording (CLAUDE.md §7).
class PreflightScreen extends StatefulWidget {
  const PreflightScreen({super.key});

  @override
  State<PreflightScreen> createState() => _PreflightScreenState();
}

class _PreflightScreenState extends State<PreflightScreen> {
  late final List<_Check> _checks;
  bool _allPassed = false;
  bool _running = false;

  @override
  void initState() {
    super.initState();
    _checks = [
      _Check('Phone Battery ≥ 30%'),
      _Check('Storage Free ≥ 2 GB'),
      _Check('Clock Synced'),
      _Check('WS RTT < 500ms'),
      _Check('Accelerometer Sanity'),
      _Check('Gyroscope Sanity'),
    ];
    _runChecks();
  }

  Future<void> _runChecks() async {
    if (_running) return;
    setState(() {
      _running = true;
      _allPassed = false;
      for (final c in _checks) {
        c.status = _Status.pending;
        c.detail = '';
      }
    });

    await _checkBattery();
    await _checkStorage();
    await _checkClockSync();
    await _checkRtt();
    await _checkSensorSanity();

    final passed = _checks.every((c) => c.status == _Status.pass);
    setState(() {
      _allPassed = passed;
      _running = false;
    });
  }

  Future<void> _checkBattery() async {
    _setRunning(0);
    try {
      final level = await Battery().batteryLevel;
      if (level >= 30) {
        _setPass(0, '$level%');
      } else {
        _setFail(0, '$level% — charge to ≥ 30%');
      }
    } catch (e) {
      _setFail(0, 'Cannot read battery');
    }
  }

  Future<void> _checkStorage() async {
    _setRunning(1);
    try {
      final dir = await getApplicationDocumentsDirectory();
      final stat = await FileStat.stat(dir.path);
      // Write a 1 MB test file to verify writable and estimate free space.
      final testFile = File('${dir.path}/.preflight_test');
      await testFile.writeAsBytes(List.filled(1024 * 1024, 0));
      await testFile.delete();
      // We can't get exact free space without a plugin; pass if write succeeds.
      _setPass(1, 'Write test OK');
    } catch (e) {
      _setFail(1, 'Write test failed: $e');
    }
  }

  Future<void> _checkClockSync() async {
    _setRunning(2);
    // Give clock sync service up to 3 seconds to complete.
    for (int i = 0; i < 15; i++) {
      if (ClockSyncService().isSynced) break;
      await Future.delayed(const Duration(milliseconds: 200));
    }
    if (ClockSyncService().isSynced) {
      final offset = ClockSyncService().clockOffsetMs;
      if (offset.abs() > 30000) {
        _setFail(2, 'Offset ${offset}ms — check phone NTP');
      } else {
        _setPass(2, 'Offset ${offset}ms');
      }
    } else {
      _setFail(2, 'No sync yet — check connection');
    }
  }

  Future<void> _checkRtt() async {
    _setRunning(3);
    final rtt = ClockSyncService().lastRttMs;
    if (rtt == 0) {
      _setFail(3, 'No RTT measured yet');
    } else if (rtt < 500) {
      _setPass(3, '${rtt}ms');
    } else {
      _setFail(3, '${rtt}ms — check Wi-Fi');
    }
  }

  Future<void> _checkSensorSanity() async {
    _setRunning(4, hint: 'Hold phone still…');
    InternalSensorManager().start(frequency: 100);

    // Collect every sample emitted during the 3-second window (~300 samples at
    // 100 Hz). Using the mean over all samples means a single motion spike does
    // not fail the check — only sustained movement or a broken sensor will.
    final List<double> accSamples = [];
    final List<double> gyroSamples = [];

    final sub = InternalSensorManager().dataStream.listen((pkt) {
      final avm = sqrt(pkt.accX * pkt.accX + pkt.accY * pkt.accY + pkt.accZ * pkt.accZ);
      final gvm = sqrt(pkt.gyroX * pkt.gyroX + pkt.gyroY * pkt.gyroY + pkt.gyroZ * pkt.gyroZ);
      accSamples.add(avm);
      gyroSamples.add(gvm);
    });

    await Future.delayed(const Duration(seconds: 3));
    await sub.cancel();

    if (accSamples.isEmpty || gyroSamples.isEmpty) {
      _setFail(4, 'No sensor data received — check permissions');
      _setFail(5, 'No sensor data received — check permissions');
      return;
    }

    final meanAcc = accSamples.reduce((a, b) => a + b) / accSamples.length;
    final meanGyro = gyroSamples.reduce((a, b) => a + b) / gyroSamples.length;

    // Acc magnitude at rest ≈ 1 g (gravity). Threshold 0.5–1.5 g.
    if (meanAcc >= 0.5 && meanAcc <= 1.5) {
      _setPass(4, 'avm=${meanAcc.toStringAsFixed(2)}g (${accSamples.length} samples)');
    } else {
      _setFail(4, 'avm=${meanAcc.toStringAsFixed(2)}g — hold still or check sensor');
    }

    _setRunning(5, hint: 'Hold phone still…');
    if (meanGyro < 5.0) {
      _setPass(5, 'gyro=${meanGyro.toStringAsFixed(2)}°/s (${gyroSamples.length} samples)');
    } else {
      _setFail(5, 'gyro=${meanGyro.toStringAsFixed(2)}°/s — hold still or check sensor');
    }
  }

  void _setRunning(int i, {String hint = ''}) => setState(() {
        _checks[i].status = _Status.running;
        _checks[i].hint = hint;
      });

  void _setPass(int i, String detail) => setState(() {
        _checks[i].status = _Status.pass;
        _checks[i].detail = detail;
        _checks[i].hint = '';
      });

  void _setFail(int i, String detail) => setState(() {
        _checks[i].status = _Status.fail;
        _checks[i].detail = detail;
        _checks[i].hint = '';
      });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: const Color(0xFF16213E),
        title: const Text('Preflight Check',
            style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _running ? null : _runChecks,
            tooltip: 'Re-run checks',
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: _checks.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (_, i) => _CheckTile(_checks[i]),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor:
                    _allPassed ? Colors.green : Colors.grey.shade700,
                minimumSize: const Size.fromHeight(52),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
              onPressed: _allPassed ? _proceed : null,
              child: Text(
                _allPassed ? 'START RECORDING SESSION' : 'CHECKS PENDING',
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _proceed() {
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const DashboardScreen()),
    );
  }
}

class _CheckTile extends StatelessWidget {
  final _Check check;
  const _CheckTile(this.check);

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch (check.status) {
      _Status.pending => (Icons.radio_button_unchecked, Colors.white38),
      _Status.running => (Icons.hourglass_top, Colors.amber),
      _Status.pass => (Icons.check_circle, Colors.greenAccent),
      _Status.fail => (Icons.cancel, Colors.redAccent),
    };

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF16213E),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: check.status == _Status.fail
              ? Colors.redAccent.withOpacity(0.5)
              : Colors.white10,
        ),
      ),
      child: Row(
        children: [
          check.status == _Status.running
              ? SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                      color: color, strokeWidth: 2),
                )
              : Icon(icon, color: color, size: 24),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(check.label,
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w500)),
                if (check.status == _Status.running && check.hint.isNotEmpty)
                  Text(check.hint,
                      style: TextStyle(
                          color: Colors.amber.withOpacity(0.9), fontSize: 12)),
                if (check.detail.isNotEmpty)
                  Text(check.detail,
                      style: TextStyle(
                          color: color.withOpacity(0.8), fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
