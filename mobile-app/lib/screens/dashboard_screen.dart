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

  final List<int> _integerOptions = List.generate(11, (index) => index);
  final List<int> _frequencyOptions = [1, 5, 10, 20, 40, 50, 100]; 
  
  int _selectedLocation = 0;
  int _selectedLabel = 0;
  int _selectedFrequency = 50; 

  @override
  void initState() {
    super.initState();
    _initStream();
  }

  void _initStream() {
    _dataSub?.cancel();

    if (_useInternalSensor) {
      InternalSensorManager().start(frequency: _selectedFrequency);
      _currentStream = InternalSensorManager().dataStream;
    } else {
      InternalSensorManager().stop();
      _currentStream = BluetoothManager().dataStream;
    }

    _dataSub = _currentStream!.listen((packet) {
      if (CsvLogger().isRecording) {
        CsvLogger().currentLocation = _selectedLocation;
        CsvLogger().currentLabel = _selectedLabel;
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
        title: const Text("IMU Collector"),
        backgroundColor: isRecording ? Colors.red : Colors.deepPurple,
        actions: [
          Row(
            children: [
              Text(_useInternalSensor ? "HP SENSORS" : "BLUETOOTH", style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
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
                    Padding(
                      padding: const EdgeInsets.all(5), 
                      child: Text(
                        "Accelerometer (${_useInternalSensor ? "$_selectedFrequency Hz" : "Ext"})", 
                        style: const TextStyle(fontWeight: FontWeight.bold)
                      )
                    ),
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
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.white,
              boxShadow: [BoxShadow(color: Colors.grey.shade300, blurRadius: 5, offset: const Offset(0, -2))],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _fileNameController,
                        decoration: const InputDecoration(
                          labelText: "File Name", 
                          border: OutlineInputBorder(), 
                          isDense: true, 
                          contentPadding: EdgeInsets.all(8)
                        ),
                        enabled: !isRecording,
                      ),
                    ),
                    const SizedBox(width: 10),
                    SizedBox(
                      height: 45,
                      width: 45,
                      child: FloatingActionButton(
                        backgroundColor: isRecording ? Colors.red : Colors.green,
                        child: Icon(isRecording ? Icons.stop : Icons.fiber_manual_record),
                        onPressed: () => _toggleRecording(),
                      ),
                    ),
                  ],
                ),
                
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      flex: 2, 
                      child: InputDecorator(
                        decoration: const InputDecoration(
                          labelText: "Freq (Hz)",
                          border: OutlineInputBorder(),
                          contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<int>(
                            value: _selectedFrequency,
                            isExpanded: true,
                            onChanged: (isRecording || !_useInternalSensor) ? null : (newValue) {
                              setState(() {
                                _selectedFrequency = newValue!;
                                _initStream(); 
                              });
                            },
                            items: _frequencyOptions.map((int value) {
                              return DropdownMenuItem<int>(
                                value: value,
                                child: Text(value.toString(), style: const TextStyle(fontSize: 13)),
                              );
                            }).toList(),
                          ),
                        ),
                      ),
                    ),

                    const SizedBox(width: 8),

                    Expanded(
                      flex: 2,
                      child: InputDecorator(
                        decoration: const InputDecoration(
                          labelText: "Location",
                          border: OutlineInputBorder(),
                          contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<int>(
                            value: _selectedLocation,
                            isExpanded: true,
                            items: _integerOptions.map((int value) {
                              return DropdownMenuItem<int>(
                                value: value,
                                child: Text(value.toString(), style: const TextStyle(fontSize: 13)),
                              );
                            }).toList(),
                            onChanged: (newValue) {
                              setState(() => _selectedLocation = newValue!);
                            },
                          ),
                        ),
                      ),
                    ),
                    
                    const SizedBox(width: 8),

                    Expanded(
                      flex: 2,
                      child: InputDecorator(
                        decoration: const InputDecoration(
                          labelText: "Label",
                          border: OutlineInputBorder(),
                          contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<int>(
                            value: _selectedLabel,
                            isExpanded: true,
                            items: _integerOptions.map((int value) {
                              return DropdownMenuItem<int>(
                                value: value,
                                child: Text(value.toString(), style: const TextStyle(fontSize: 13)),
                              );
                            }).toList(),
                            onChanged: (newValue) {
                              setState(() => _selectedLabel = newValue!);
                            },
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                
                Padding(
                  padding: const EdgeInsets.only(top: 8.0),
                  child: Text(
                    "STATUS: $_statusMessage | REC: ${isRecording ? "ON" : "OFF"}",
                    style: TextStyle(
                      fontSize: 11, 
                      fontWeight: FontWeight.bold, 
                      color: isRecording ? Colors.red : Colors.grey
                    ),
                  ),
                ),
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
      setState(() => _statusMessage = "File Saved.");
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Data saved successfully!")));
    } else {
      CsvLogger().currentLocation = _selectedLocation;
      CsvLogger().currentLabel = _selectedLabel;
      
      String path = await CsvLogger().startRecording(_fileNameController.text);
      setState(() => _statusMessage = "Rec $_selectedFrequency Hz...");
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Saving to $path")));
    }
  }
}