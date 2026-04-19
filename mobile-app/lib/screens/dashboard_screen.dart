import 'package:flutter/material.dart';

import '../models/node_config.dart';
import '../services/backend_client.dart';
import '../services/device_node_controller.dart';
import '../services/local_store.dart';
import '../services/node_config_store.dart';
import '../services/sensor_sampler.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late final DeviceNodeController _controller;
  late final TextEditingController _backendController;
  late final TextEditingController _wsPortController;
  late final TextEditingController _deviceIdController;
  late final TextEditingController _deviceRoleController;
  late final TextEditingController _displayNameController;
  late final TextEditingController _sessionIdController;

  @override
  void initState() {
    super.initState();
    _controller = DeviceNodeController(
      configStore: NodeConfigStore(),
      localStore: LocalStore.instance,
      backendClient: BackendClient(),
      sensorSampler: SensorSampler(),
    );

    _backendController = TextEditingController();
    _wsPortController = TextEditingController();
    _deviceIdController = TextEditingController();
    _deviceRoleController = TextEditingController();
    _displayNameController = TextEditingController();
    _sessionIdController = TextEditingController();

    _controller.initialize().then((_) {
      final config = _controller.config;
      _backendController.text = config.backendBaseUrl;
      _wsPortController.text = config.wsPort.toString();
      _deviceIdController.text = config.deviceId;
      _deviceRoleController.text = config.deviceRole;
      _displayNameController.text = config.displayName;
      _sessionIdController.text = config.sessionId;
      if (mounted) {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _controller.disposeController();
    _controller.dispose();

    _backendController.dispose();
    _wsPortController.dispose();
    _deviceIdController.dispose();
    _deviceRoleController.dispose();
    _displayNameController.dispose();
    _sessionIdController.dispose();
    super.dispose();
  }

  Future<void> _saveConfig() async {
    final wsPort = int.tryParse(_wsPortController.text.trim()) ?? 8001;
    final nextConfig = NodeConfig(
      backendBaseUrl: _backendController.text.trim(),
      wsPort: wsPort,
      deviceId: _deviceIdController.text.trim().toUpperCase(),
      deviceRole: _deviceRoleController.text.trim().toLowerCase(),
      displayName: _displayNameController.text.trim(),
      sessionId: _sessionIdController.text.trim().toUpperCase(),
    );
    await _controller.saveConfig(nextConfig);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Config tersimpan')));
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final state = _controller.state;
        return Scaffold(
          appBar: AppBar(
            title: const Text('IMU Mobile Node (Phase 8)'),
            backgroundColor: state.recording ? Colors.red : Colors.blueGrey,
          ),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _sectionCard(
                  title: 'Setup',
                  children: [
                    _textField('Backend URL', _backendController),
                    const SizedBox(height: 8),
                    _textField('WS Port', _wsPortController, keyboardType: TextInputType.number),
                    const SizedBox(height: 8),
                    _textField('Device ID', _deviceIdController),
                    const SizedBox(height: 8),
                    _textField('Device Role (chest/waist/thigh/other)', _deviceRoleController),
                    const SizedBox(height: 8),
                    _textField('Display Name', _displayNameController),
                    const SizedBox(height: 8),
                    _textField('Session ID aktif', _sessionIdController),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton(
                            onPressed: _saveConfig,
                            child: const Text('Save Config'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: ElevatedButton(
                            onPressed: state.connected ? null : () => _controller.connect(),
                            child: const Text('Connect'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: OutlinedButton(
                            onPressed: state.connected ? () => _controller.disconnect() : null,
                            child: const Text('Disconnect'),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                _sectionCard(
                  title: 'Runtime Status',
                  children: [
                    _statusRow('Connection', state.connected ? 'online' : 'offline'),
                    _statusRow('Recording', state.recording ? 'running' : 'stopped'),
                    _statusRow('Current Session', state.sessionId.isEmpty ? '-' : state.sessionId),
                    _statusRow('Last Seq', state.lastSeq.toString()),
                    _statusRow('Local Samples', state.localSamples.toString()),
                    _statusRow('Pending Upload', state.pendingSamples.toString()),
                    _statusRow('Effective Hz', state.effectiveHz.toStringAsFixed(1)),
                    _statusRow('Battery', state.batteryPercent == null ? '-' : '${state.batteryPercent}%'),
                    _statusRow('Storage Free', state.storageFreeMb == null ? '-' : '${state.storageFreeMb} MB'),
                    _statusRow('Info', state.lastInfo),
                  ],
                ),
                const SizedBox(height: 10),
                _sectionCard(
                  title: 'Operational Notes',
                  children: const [
                    Text('1. Isi Session ID yang valid (format backend) sebelum connect.'),
                    SizedBox(height: 4),
                    Text('2. Saat backend kirim START_SESSION, app otomatis sampling 100 Hz, simpan lokal, dan upload batch protobuf.'),
                    SizedBox(height: 4),
                    Text('3. Jika network putus, sample tetap disimpan lokal dan dikirim ulang saat reconnect.'),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _sectionCard({required String title, required List<Widget> children}) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _textField(String label, TextEditingController controller, {TextInputType? keyboardType}) {
    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        isDense: true,
      ),
    );
  }

  Widget _statusRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(flex: 2, child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600))),
          Expanded(flex: 3, child: Text(value)),
        ],
      ),
    );
  }
}