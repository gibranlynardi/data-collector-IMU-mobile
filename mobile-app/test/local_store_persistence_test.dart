import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sensors_app/models/sample_frame.dart';
import 'package:sensors_app/services/local_store.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void main() {
  test('sample sebelum crash tetap aman di sqlite', () async {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;

    final tempDir = await Directory.systemTemp.createTemp('imu-store-test-');
    final dbPath = '${tempDir.path}${Platform.pathSeparator}imu_node_test.db';

    const sessionId = '20260419_143022_A1B2C3D4';
    const deviceId = 'DEVICE-CHEST-001';

    final firstRunStore = LocalStore.forTest(dbPath: dbPath);
    await firstRunStore.upsertSession(sessionId: sessionId, status: 'running');
    await firstRunStore.insertSample(
      sessionId: sessionId,
      deviceId: deviceId,
      deviceRole: 'chest',
      seq: 1,
      frame: const SampleFrame(
        timestampDeviceUnixNs: 111,
        elapsedMs: 11,
        accXG: 0.1,
        accYG: 0.2,
        accZG: 0.3,
        gyroXDeg: 1,
        gyroYDeg: 2,
        gyroZDeg: 3,
      ),
    );

    expect(await firstRunStore.pendingCount(sessionId: sessionId, deviceId: deviceId), 1);
    final firstRunDb = await firstRunStore.database();
    await firstRunDb.close();

    final afterCrashStore = LocalStore.forTest(dbPath: dbPath);
    expect(await afterCrashStore.latestUnfinishedSessionId(), sessionId);
    expect(await afterCrashStore.pendingCount(sessionId: sessionId, deviceId: deviceId), 1);
    expect(await afterCrashStore.getLastSeq(sessionId, deviceId), 1);

    final secondRunDb = await afterCrashStore.database();
    await secondRunDb.close();
    await tempDir.delete(recursive: true);
  });

  test('duplicate seq untuk session-device yang sama diabaikan oleh unique index', () async {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;

    final tempDir = await Directory.systemTemp.createTemp('imu-store-dup-test-');
    final dbPath = '${tempDir.path}${Platform.pathSeparator}imu_node_dup_test.db';

    const sessionId = '20260419_143022_A1B2C3D4';
    const deviceId = 'DEVICE-CHEST-001';

    final store = LocalStore.forTest(dbPath: dbPath);
    await store.upsertSession(sessionId: sessionId, status: 'running');

    const frame = SampleFrame(
      timestampDeviceUnixNs: 111,
      elapsedMs: 11,
      accXG: 0.1,
      accYG: 0.2,
      accZG: 0.3,
      gyroXDeg: 1,
      gyroYDeg: 2,
      gyroZDeg: 3,
    );

    await store.insertSample(
      sessionId: sessionId,
      deviceId: deviceId,
      deviceRole: 'chest',
      seq: 1,
      frame: frame,
    );
    await store.insertSample(
      sessionId: sessionId,
      deviceId: deviceId,
      deviceRole: 'chest',
      seq: 1,
      frame: frame,
    );

    expect(await store.totalSampleCount(sessionId: sessionId, deviceId: deviceId), 1);
    expect(await store.getLastSeq(sessionId, deviceId), 1);

    final db = await store.database();
    await db.close();
    await tempDir.delete(recursive: true);
  });
}
