import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import '../models/pending_sample.dart';
import '../models/sample_frame.dart';

class LocalStore {
  LocalStore._();

  static final LocalStore instance = LocalStore._();

  Database? _db;

  Future<Database> database() async {
    if (_db != null) {
      return _db!;
    }
    final docsDir = await getApplicationDocumentsDirectory();
    final dbPath = p.join(docsDir.path, 'imu_node.db');
    _db = await openDatabase(
      dbPath,
      version: 2,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE local_sessions(
            session_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            server_start_time_unix_ns INTEGER,
            monotonic_start_ms INTEGER,
            stopped_at_unix_ns INTEGER,
            last_seq INTEGER NOT NULL DEFAULT 0,
            updated_at_unix_ns INTEGER NOT NULL
          )
        ''');

        await db.execute('''
          CREATE TABLE sensor_samples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_role TEXT NOT NULL,
            seq INTEGER NOT NULL,
            timestamp_device_unix_ns INTEGER NOT NULL,
            elapsed_ms INTEGER NOT NULL,
            acc_x_g REAL NOT NULL,
            acc_y_g REAL NOT NULL,
            acc_z_g REAL NOT NULL,
            gyro_x_deg REAL NOT NULL,
            gyro_y_deg REAL NOT NULL,
            gyro_z_deg REAL NOT NULL,
            inflight INTEGER NOT NULL DEFAULT 0,
            uploaded INTEGER NOT NULL DEFAULT 0,
            created_at_unix_ns INTEGER NOT NULL
          )
        ''');

        await db.execute('CREATE INDEX idx_sensor_pending ON sensor_samples(session_id, device_id, uploaded, seq)');

        await db.execute('''
          CREATE TABLE upload_batches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            start_seq INTEGER NOT NULL,
            end_seq INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 1,
            last_error TEXT,
            updated_at_unix_ns INTEGER NOT NULL
          )
        ''');
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          await db.execute('ALTER TABLE sensor_samples ADD COLUMN inflight INTEGER NOT NULL DEFAULT 0');
        }
      },
    );
    return _db!;
  }

  Future<void> upsertSession({
    required String sessionId,
    required String status,
    int? serverStartUnixNs,
    int? monotonicStartMs,
    int? stoppedAtUnixNs,
  }) async {
    final db = await database();
    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
    await db.insert(
      'local_sessions',
      {
        'session_id': sessionId,
        'status': status,
        'server_start_time_unix_ns': serverStartUnixNs,
        'monotonic_start_ms': monotonicStartMs,
        'stopped_at_unix_ns': stoppedAtUnixNs,
        'updated_at_unix_ns': nowNs,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> updateSessionStatus(String sessionId, String status, {int? stoppedAtUnixNs}) async {
    final db = await database();
    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
    await db.update(
      'local_sessions',
      {
        'status': status,
        'stopped_at_unix_ns': stoppedAtUnixNs,
        'updated_at_unix_ns': nowNs,
      },
      where: 'session_id = ?',
      whereArgs: [sessionId],
    );
  }

  Future<void> updateSessionStartMarkers({
    required String sessionId,
    int? serverStartUnixNs,
    int? monotonicStartMs,
  }) async {
    final db = await database();
    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
    await db.update(
      'local_sessions',
      {
        'server_start_time_unix_ns': serverStartUnixNs,
        'monotonic_start_ms': monotonicStartMs,
        'updated_at_unix_ns': nowNs,
      },
      where: 'session_id = ?',
      whereArgs: [sessionId],
    );
  }

  Future<String?> latestUnfinishedSessionId() async {
    final db = await database();
    final rows = await db.query(
      'local_sessions',
      columns: ['session_id'],
      where: 'status != ?',
      whereArgs: ['stopped'],
      orderBy: 'updated_at_unix_ns DESC',
      limit: 1,
    );
    if (rows.isEmpty) {
      return null;
    }
    return rows.first['session_id'] as String?;
  }

  Future<int> getLastSeq(String sessionId, String deviceId) async {
    final db = await database();
    final rows = await db.rawQuery(
      'SELECT COALESCE(MAX(seq), 0) AS max_seq FROM sensor_samples WHERE session_id = ? AND device_id = ?',
      [sessionId, deviceId],
    );
    final value = rows.first['max_seq'];
    return value is int ? value : 0;
  }

  Future<void> insertSample({
    required String sessionId,
    required String deviceId,
    required String deviceRole,
    required int seq,
    required SampleFrame frame,
  }) async {
    final db = await database();
    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;

    await db.insert('sensor_samples', {
      'session_id': sessionId,
      'device_id': deviceId,
      'device_role': deviceRole,
      'seq': seq,
      'timestamp_device_unix_ns': frame.timestampDeviceUnixNs,
      'elapsed_ms': frame.elapsedMs,
      'acc_x_g': frame.accXG,
      'acc_y_g': frame.accYG,
      'acc_z_g': frame.accZG,
      'gyro_x_deg': frame.gyroXDeg,
      'gyro_y_deg': frame.gyroYDeg,
      'gyro_z_deg': frame.gyroZDeg,
      'inflight': 0,
      'uploaded': 0,
      'created_at_unix_ns': nowNs,
    });

    await db.update(
      'local_sessions',
      {
        'last_seq': seq,
        'updated_at_unix_ns': nowNs,
      },
      where: 'session_id = ?',
      whereArgs: [sessionId],
    );
  }

  Future<List<PendingSample>> fetchPendingSamples({
    required String sessionId,
    required String deviceId,
    int limit = 250,
  }) async {
    final db = await database();
    final rows = await db.query(
      'sensor_samples',
      where: 'session_id = ? AND device_id = ? AND uploaded = 0 AND inflight = 0',
      whereArgs: [sessionId, deviceId],
      orderBy: 'seq ASC',
      limit: limit,
    );
    return rows.map(PendingSample.fromRow).toList();
  }

  Future<void> markInflightRange({
    required String sessionId,
    required String deviceId,
    required int startSeq,
    required int endSeq,
  }) async {
    final db = await database();
    await db.update(
      'sensor_samples',
      {'inflight': 1},
      where: 'session_id = ? AND device_id = ? AND seq >= ? AND seq <= ? AND uploaded = 0',
      whereArgs: [sessionId, deviceId, startSeq, endSeq],
    );
  }

  Future<void> clearInflightRange({
    required String sessionId,
    required String deviceId,
    required int startSeq,
    required int endSeq,
  }) async {
    final db = await database();
    await db.update(
      'sensor_samples',
      {'inflight': 0},
      where: 'session_id = ? AND device_id = ? AND seq >= ? AND seq <= ? AND uploaded = 0',
      whereArgs: [sessionId, deviceId, startSeq, endSeq],
    );
  }

  Future<void> clearAllInflight({
    required String sessionId,
    required String deviceId,
  }) async {
    final db = await database();
    await db.update(
      'sensor_samples',
      {'inflight': 0},
      where: 'session_id = ? AND device_id = ? AND uploaded = 0',
      whereArgs: [sessionId, deviceId],
    );
  }

  Future<void> markUploadedThroughSeq({
    required String sessionId,
    required String deviceId,
    required int lastReceivedSeq,
  }) async {
    final db = await database();
    await db.update(
      'sensor_samples',
      {'uploaded': 1, 'inflight': 0},
      where: 'session_id = ? AND device_id = ? AND seq <= ?',
      whereArgs: [sessionId, deviceId, lastReceivedSeq],
    );
  }

  Future<void> resetUploadFlagsAfterSeq({
    required String sessionId,
    required String deviceId,
    required int backendLastSeq,
  }) async {
    final db = await database();
    await db.update(
      'sensor_samples',
      {'uploaded': 0, 'inflight': 0},
      where: 'session_id = ? AND device_id = ? AND seq > ?',
      whereArgs: [sessionId, deviceId, backendLastSeq],
    );
  }

  Future<int> pendingCount({required String sessionId, required String deviceId}) async {
    final db = await database();
    final rows = await db.rawQuery(
      'SELECT COUNT(*) AS c FROM sensor_samples WHERE session_id = ? AND device_id = ? AND uploaded = 0',
      [sessionId, deviceId],
    );
    final value = rows.first['c'];
    return value is int ? value : 0;
  }

  Future<int> totalSampleCount({required String sessionId, required String deviceId}) async {
    final db = await database();
    final rows = await db.rawQuery(
      'SELECT COUNT(*) AS c FROM sensor_samples WHERE session_id = ? AND device_id = ?',
      [sessionId, deviceId],
    );
    final value = rows.first['c'];
    return value is int ? value : 0;
  }

  Future<void> insertUploadBatch({
    required String sessionId,
    required String deviceId,
    required int startSeq,
    required int endSeq,
    required int sampleCount,
    required String status,
    String? lastError,
  }) async {
    final db = await database();
    final nowNs = DateTime.now().microsecondsSinceEpoch * 1000;
    await db.insert('upload_batches', {
      'session_id': sessionId,
      'device_id': deviceId,
      'start_seq': startSeq,
      'end_seq': endSeq,
      'sample_count': sampleCount,
      'status': status,
      'last_error': lastError,
      'updated_at_unix_ns': nowNs,
    });
  }
}
