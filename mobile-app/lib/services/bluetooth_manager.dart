import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_bluetooth_serial/flutter_bluetooth_serial.dart';
import '../models/sensor_packet.dart';

class BluetoothManager {
  static final BluetoothManager _instance = BluetoothManager._internal();
  factory BluetoothManager() => _instance;
  BluetoothManager._internal();

  BluetoothConnection? _connection;
  final StreamController<SensorPacket> _dataStreamController = StreamController.broadcast();
  Stream<SensorPacket> get dataStream => _dataStreamController.stream;

  List<int> _buffer = [];
  bool isConnected = false;

  Future<List<BluetoothDevice>> scanDevices() async {
    try {
      return await FlutterBluetoothSerial.instance.getBondedDevices();
    } catch (e) {
      print("Error scanning: $e");
      return [];
    }
  }

  Future<bool> connectToDevice(BluetoothDevice device) async {
    if (_connection != null) await disconnect();

    try {
      _connection = await BluetoothConnection.toAddress(device.address);
      isConnected = true;
      print("Connected to ${device.name}");

      _connection!.input!.listen(_onDataReceived).onDone(() {
        isConnected = false;
        print("Disconnected remotely");
      });

      return true;
    } catch (e) {
      print("Connection failed: $e");
      return false;
    }
  }

  Future<void> disconnect() async {
    await _connection?.finish();
    _connection = null;
    isConnected = false;
  }

  void _onDataReceived(Uint8List data) {
    _buffer.addAll(data);

    while (_buffer.contains(10)) { 
      int index = _buffer.indexOf(10);
      List<int> rawMessage = _buffer.sublist(0, index);
      _buffer = _buffer.sublist(index + 1);

      String text = utf8.decode(rawMessage).trim();
      _parseAndEmit(text);
    }
  }

  void _parseAndEmit(String text) {
    try {
      List<String> parts = text.split(',');
      
      if (parts.length == 6) {
        double ax = double.parse(parts[0]);
        double ay = double.parse(parts[1]);
        double az = double.parse(parts[2]);
        double gx = double.parse(parts[3]);
        double gy = double.parse(parts[4]);
        double gz = double.parse(parts[5]);

        _dataStreamController.add(SensorPacket(
          accX: ax, accY: ay, accZ: az,
          gyroX: gx, gyroY: gy, gyroZ: gz,
          timestamp: DateTime.now(),
        ));
      } else {
      }
    } catch (e) {
      //
    }
  }
}