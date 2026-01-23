import 'package:flutter/material.dart';
import 'dart:async';
import '../services/bluetooth_manager.dart';
import '../services/internal_sensor_manager.dart';
import '../services/csv_logger.dart';
import '../widgets/graph_widget.dart';
import '../models/sensor_packet.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  _DashboardScreenState createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final TextEditingController _fileNameController = TextEditingController(text: "Activity_Data");
  String _statusMessage = "Ready";
  
  bool _useInternalSensor = false; 
  StreamSubscription? _dataSub;
  Stream<SensorPacket>? _currentStream;

  final List<String> _activities = ["IDLE", "WALK", "RUN", "JUMP", "FALL", "SIT"];

  @override
  void initState() {
    super.initState();
    _initStream();
  }

  void _initStream() {
    _dataSub?.cancel();

    if (_useInternalSensor) {
      InternalSensorManager().start();
      _currentStream = InternalSensorManager().dataStream;
    } else {
      InternalSensorManager().stop();
      _currentStream = BluetoothManager().dataStream;
    }

   
    _dataSub = _currentStream!.listen((packet) {
      if (CsvLogger().isRecording) {
        CsvLogger().writePacket(packet);
      }
    });
    
    setState(() {});
  }

  @override
  void dispose() {
    _dataSub?.cancel();
    InternalSensorManager().stop(); 
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isRecording = CsvLogger().isRecording;

    return Scaffold(
      appBar: AppBar(
        title: const Text("6-Axis Logger"),
        backgroundColor: isRecording ? Colors.red : Colors.deepPurple,
        actions: [
          Row(
            children: [
              Icon(_useInternalSensor ? Icons.phone_android : Icons.memory, size: 20),
              const SizedBox(width: 5),
              Switch(
                value: _useInternalSensor,
                activeColor: Colors.orange,
                onChanged: (val) {
                  setState(() {
                    _useInternalSensor = val;
                    _initStream();
                  });
                },
              ),
            ],
          )
        ],
      ),
      body: Column(
        children: [
          Expanded(
            flex: 2,
            child: _currentStream == null 
              ? const Center(child: CircularProgressIndicator()) 
              : ListView(
                  padding: const EdgeInsets.all(5),
                  children: [
                    const Padding(padding: EdgeInsets.all(5), child: Text("Accelerometer", style: TextStyle(fontWeight: FontWeight.bold))),
                    GraphWidget(size: const Size(double.infinity, 100), maxPoints: 100, dataStream: _currentStream!, sensorType: 'accel', axis: 'x'),
                    GraphWidget(size: const Size(double.infinity, 100), maxPoints: 100, dataStream: _currentStream!, sensorType: 'accel', axis: 'y'),
                    GraphWidget(size: const Size(double.infinity, 100), maxPoints: 100, dataStream: _currentStream!, sensorType: 'accel', axis: 'z'),
                    
                    const Padding(padding: EdgeInsets.all(5), child: Text("Gyroscope", style: TextStyle(fontWeight: FontWeight.bold))),
                    GraphWidget(size: const Size(double.infinity, 100), maxPoints: 100, dataStream: _currentStream!, sensorType: 'gyro', axis: 'x'),
                    GraphWidget(size: const Size(double.infinity, 100), maxPoints: 100, dataStream: _currentStream!, sensorType: 'gyro', axis: 'y'),
                    GraphWidget(size: const Size(double.infinity, 100), maxPoints: 100, dataStream: _currentStream!, sensorType: 'gyro', axis: 'z'),
                  ],
                ),
          ),

          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.grey.shade100,
            child: Column(
              children: [
                Text("MODE: ${_useInternalSensor ? "INTERNAL HP" : "BLUETOOTH ARDUINO"}", 
                  style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.indigo)),
                const SizedBox(height: 5),
                Text("Label: ${CsvLogger().currentLabel}", style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.blue)),
                
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _fileNameController,
                        decoration: const InputDecoration(labelText: "File Name", border: OutlineInputBorder(), isDense: true),
                        enabled: !isRecording,
                      ),
                    ),
                    const SizedBox(width: 10),
                    FloatingActionButton(
                      backgroundColor: isRecording ? Colors.red : Colors.green,
                      child: Icon(isRecording ? Icons.stop : Icons.fiber_manual_record),
                      onPressed: () => _toggleRecording(),
                    ),
                  ],
                ),
                
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  children: _activities.map((label) {
                    return ChoiceChip(
                      label: Text(label),
                      selected: CsvLogger().currentLabel == label,
                      onSelected: (_) => setState(() => CsvLogger().currentLabel = label),
                    );
                  }).toList(),
                )
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _toggleRecording() async {
    if (CsvLogger().isRecording) {
      await CsvLogger().stopRecording();
      setState(() => _statusMessage = "Saved.");
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("File saved!")));
    } else {
      String path = await CsvLogger().startRecording(_fileNameController.text);
      setState(() => _statusMessage = "Rec...");
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Saving to $path")));
    }
  }
}