import 'package:flutter/material.dart';
import 'package:flutter_bluetooth_serial/flutter_bluetooth_serial.dart';
import 'package:permission_handler/permission_handler.dart';
import '../services/bluetooth_manager.dart';
import 'dashboard_screen.dart';

class ConnectionScreen extends StatefulWidget {
  const ConnectionScreen({super.key});

  @override
  _ConnectionScreenState createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  List<BluetoothDevice> _devices = [];
  bool _isScanning = false;

  @override
  void initState() {
    super.initState();
    _checkPermissions();
  }

  Future<void> _checkPermissions() async {
    // Request multiple permissions required for Bluetooth on Android 12+ and below
    await [
      Permission.bluetooth,
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
      Permission.location, // Required for scanning on older Android
    ].request();
    
    _startScan();
  }

  Future<void> _startScan() async {
    setState(() => _isScanning = true);
    // Get paired devices (HC-05 is usually paired in Android Settings first)
    List<BluetoothDevice> devices = await BluetoothManager().scanDevices();
    setState(() {
      _devices = devices;
      _isScanning = false;
    });
  }

  Future<void> _connect(BluetoothDevice device) async {
    // Show loading dialog
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (c) => const Center(child: CircularProgressIndicator()),
    );

    bool success = await BluetoothManager().connectToDevice(device);

    Navigator.pop(context); // Close loading dialog

    if (success) {
      // Navigate to Dashboard
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => const DashboardScreen()),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Connection failed. Is the device on?")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Connect to Sensor"),
        backgroundColor: Colors.deepPurple,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _startScan,
          )
        ],
      ),
      body: _isScanning
          ? const Center(child: CircularProgressIndicator())
          : _devices.isEmpty
              ? const Center(child: Text("No paired devices found.\nPair HC-05 in Android Settings first."))
              : ListView.builder(
                  itemCount: _devices.length,
                  itemBuilder: (context, index) {
                    final device = _devices[index];
                    return ListTile(
                      leading: const Icon(Icons.bluetooth),
                      title: Text(device.name ?? "Unknown Device"),
                      subtitle: Text(device.address),
                      trailing: ElevatedButton(
                        child: const Text("Connect"),
                        onPressed: () => _connect(device),
                      ),
                    );
                  },
                ),
    );
  }
}