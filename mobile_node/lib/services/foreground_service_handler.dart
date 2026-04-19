import 'package:flutter_foreground_task/flutter_foreground_task.dart';

// Keeps the process alive during recording (CLAUDE.md §9.3).
class ForegroundServiceHandler {
  static final ForegroundServiceHandler _instance =
      ForegroundServiceHandler._internal();
  factory ForegroundServiceHandler() => _instance;
  ForegroundServiceHandler._internal();

  static void initOptions() {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'imu_telemetry',
        channelName: 'IMU Telemetry Service',
        channelDescription: 'Active during IMU data recording sessions',
        channelImportance: NotificationChannelImportance.HIGH,
        priority: NotificationPriority.HIGH,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(5000),
        autoRunOnBoot: true,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  Future<void> start() async {
    if (await FlutterForegroundTask.isRunningService) return;
    await FlutterForegroundTask.startService(
      notificationTitle: 'IMU Telemetry',
      notificationText: 'Connecting...',
      callback: _startCallback,
    );
  }

  Future<void> stop() async {
    await FlutterForegroundTask.stopService();
  }

  void updateNotification(int sent, int buffered) {
    final text = buffered > 0
        ? 'Recording: $sent sent, $buffered buffered'
        : 'Recording: $sent packets sent';
    FlutterForegroundTask.updateService(notificationText: text);
  }
}

@pragma('vm:entry-point')
void _startCallback() {
  FlutterForegroundTask.setTaskHandler(_ImuTaskHandler());
}

class _ImuTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {
    // Notification text is updated via ForegroundServiceHandler.updateNotification().
  }

  @override
  Future<void> onDestroy(DateTime timestamp) async {}
}
