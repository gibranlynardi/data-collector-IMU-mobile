import 'dart:io';
import 'dart:async';
import 'package:csv/csv.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import '../models/sensor_packet.dart';

class CsvLogger {
  static final CsvLogger _instance = CsvLogger._internal();
  factory CsvLogger() => _instance;
  CsvLogger._internal();

  File? _currentFile;
  IOSink? _sink;
  bool isRecording = false;
  
  int currentLocation = 0; 
  int currentLabel = 0;

  Future<String> startRecording(String fileName) async {
    if (isRecording) return "Already recording";

    if (Platform.isAndroid) {
      if (await Permission.storage.request().isDenied) {
        await Permission.manageExternalStorage.request();
      }
    }

    try {
      Directory? dir;
      if (Platform.isAndroid) {
        dir = await getExternalStorageDirectory();
      } else {
        dir = await getApplicationDocumentsDirectory();
      }

      if (dir == null) return "Error: No storage found";

      String timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
      String cleanFileName = fileName.replaceAll(' ', '_');
      String fullPath = '${dir.path}/${cleanFileName}_$timestamp.csv';
      
      _currentFile = File(fullPath);
      _sink = _currentFile!.openWrite();

      _sink!.writeln("timestamp,acc_X_g,acc_Y_g,acc_Z_g,gyro_X_deg,gyro_Y_deg,gyro_Z_deg,location,label");

      isRecording = true;
      return fullPath;
      
    } catch (e) {
      return "Error: $e";
    }
  }

  Future<void> stopRecording() async {
    if (!isRecording) return;
    await _sink?.flush();
    await _sink?.close();
    isRecording = false;
    _currentFile = null;
  }

  void writePacket(SensorPacket packet) {
    if (_sink == null || !isRecording) return;

    List<dynamic> row = packet.toCsvRow(currentLocation, currentLabel);

    String csvLine = const ListToCsvConverter().convert([row]);
    _sink!.writeln(csvLine);
  }
}