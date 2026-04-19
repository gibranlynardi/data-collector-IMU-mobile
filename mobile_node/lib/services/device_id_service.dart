import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class DeviceIdService {
  static final DeviceIdService _instance = DeviceIdService._internal();
  factory DeviceIdService() => _instance;
  DeviceIdService._internal();

  static const _key = 'device_id';
  String? _cachedId;

  Future<String> getDeviceId() async {
    if (_cachedId != null) return _cachedId!;
    final prefs = await SharedPreferences.getInstance();
    String? id = prefs.getString(_key);
    if (id == null) {
      id = const Uuid().v4();
      await prefs.setString(_key, id);
    }
    _cachedId = id;
    return id;
  }

  Future<String> getDeviceRole() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('device_role') ?? 'chest';
  }

  Future<void> setDeviceRole(String role) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_role', role);
  }

  Future<String> getLastServerIp() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('last_server_ip') ?? '';
  }

  Future<void> saveServerIp(String ip) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('last_server_ip', ip);
  }
}
