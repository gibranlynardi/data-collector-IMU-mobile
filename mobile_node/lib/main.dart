import 'package:flutter/material.dart';
import 'services/foreground_service_handler.dart';
import 'services/session_persistence.dart';
import 'services/websocket_client.dart';
import 'screens/connection_screen.dart';
import 'screens/dashboard_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  ForegroundServiceHandler.initOptions();
  runApp(const ImuTelemetryApp());
}

class ImuTelemetryApp extends StatefulWidget {
  const ImuTelemetryApp({super.key});

  @override
  State<ImuTelemetryApp> createState() => _ImuTelemetryAppState();
}

class _ImuTelemetryAppState extends State<ImuTelemetryApp> {
  Widget _home = const ConnectionScreen();
  bool _checked = false;

  @override
  void initState() {
    super.initState();
    _checkResumeSession();
  }

  // If there was an interrupted RECORDING session, try to resume it (CLAUDE.md §9.2).
  Future<void> _checkResumeSession() async {
    final interrupted = await SessionPersistence().loadInterrupted();
    if (interrupted != null) {
      final serverIp = interrupted['server_ip'] as String? ?? '';

      if (serverIp.isNotEmpty) {
        final ok = await WebSocketClient().connect(serverIp);
        if (ok) {
          setState(() => _home = const DashboardScreen());
        }
      }
    }
    setState(() => _checked = true);
  }

  @override
  Widget build(BuildContext context) {
    if (!_checked) {
      return const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          backgroundColor: Color(0xFF1A1A2E),
          body: Center(child: CircularProgressIndicator()),
        ),
      );
    }
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        colorScheme: ColorScheme.dark(
          primary: Colors.deepPurpleAccent,
          secondary: Colors.deepPurpleAccent.shade100,
        ),
      ),
      home: _home,
    );
  }
}
