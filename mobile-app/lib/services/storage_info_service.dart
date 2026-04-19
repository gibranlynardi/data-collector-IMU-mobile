import 'package:flutter/services.dart';

class StorageInfoService {
  static const MethodChannel _channel = MethodChannel('imu_node/storage');

  Future<int?> getFreeStorageMb() async {
    try {
      final result = await _channel.invokeMethod<int>('getFreeStorageMb');
      if (result == null || result < 0) {
        return null;
      }
      return result;
    } catch (_) {
      return null;
    }
  }
}
