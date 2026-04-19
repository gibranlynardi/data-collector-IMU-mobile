import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:path_provider/path_provider.dart';

// Length-delimited protobuf binary buffer for network-offline periods (CLAUDE.md §9.1).
// Format: [4-byte BE length][proto bytes] repeated.
class FallbackBufferManager {
  static final FallbackBufferManager _instance =
      FallbackBufferManager._internal();
  factory FallbackBufferManager() => _instance;
  FallbackBufferManager._internal();

  static const _maxFileSizeBytes = 500 * 1024 * 1024; // 500 MB
  static const _maxRotations = 3;
  static const _fsyncIntervalMs = 1000;

  RandomAccessFile? _raf;
  int _currentFileIndex = 1;
  int _bufferedCount = 0;
  Timer? _fsyncTimer;
  bool _isActive = false;

  int get bufferedCount => _bufferedCount;
  bool get isActive => _isActive;

  Future<File> _fileForIndex(int index) async {
    final dir = await getApplicationDocumentsDirectory();
    final suffix = index == 1 ? '' : '.$index';
    return File('${dir.path}/fallback_buffer$suffix.bin');
  }

  Future<void> activate() async {
    if (_isActive) return;
    _isActive = true;
    _bufferedCount = 0;
    await _openCurrentFile();
    _fsyncTimer = Timer.periodic(
      const Duration(milliseconds: _fsyncIntervalMs),
      (_) => _raf?.flush(),
    );
  }

  Future<void> _openCurrentFile() async {
    final f = await _fileForIndex(_currentFileIndex);
    _raf = await f.open(mode: FileMode.append);
    // Rotate if over size limit
    final stat = await f.stat();
    if (stat.size >= _maxFileSizeBytes) {
      await _rotate();
    }
  }

  Future<void> _rotate() async {
    await _raf?.close();
    _currentFileIndex++;
    if (_currentFileIndex > _maxRotations) {
      // Overwrite oldest (index 1)
      _currentFileIndex = 1;
      final f = await _fileForIndex(1);
      await f.writeAsBytes([], mode: FileMode.write); // truncate
    }
    _raf = await (await _fileForIndex(_currentFileIndex))
        .open(mode: FileMode.append);
  }

  Future<void> write(Uint8List packetBytes) async {
    if (!_isActive || _raf == null) return;
    // 4-byte big-endian length prefix
    final lenBuf = ByteData(4)..setUint32(0, packetBytes.length, Endian.big);
    await _raf!.writeFrom(lenBuf.buffer.asUint8List());
    await _raf!.writeFrom(packetBytes);
    _bufferedCount++;

    final pos = await _raf!.position();
    if (pos >= _maxFileSizeBytes) await _rotate();
  }

  // Yields each buffered packet in order from all rotation files.
  Stream<Uint8List> flushStream() async* {
    await _raf?.flush();
    await _raf?.close();
    _raf = null;

    for (int idx = 1; idx <= _maxRotations; idx++) {
      final f = await _fileForIndex(idx);
      if (!await f.exists()) continue;
      final bytes = await f.readAsBytes();
      int pos = 0;
      while (pos + 4 <= bytes.length) {
        final len = ByteData.view(bytes.buffer, pos, 4).getUint32(0, Endian.big);
        pos += 4;
        if (pos + len > bytes.length) break;
        yield Uint8List.view(bytes.buffer, pos, len);
        pos += len;
      }
    }
  }

  Future<void> clearAfterFlush() async {
    for (int idx = 1; idx <= _maxRotations; idx++) {
      final f = await _fileForIndex(idx);
      if (await f.exists()) await f.writeAsBytes([], mode: FileMode.write);
    }
    _bufferedCount = 0;
    _currentFileIndex = 1;
    _isActive = false;
    _fsyncTimer?.cancel();
  }

  Future<void> deactivate() async {
    _fsyncTimer?.cancel();
    await _raf?.flush();
    await _raf?.close();
    _raf = null;
    _isActive = false;
  }
}
