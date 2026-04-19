import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/node_config.dart';

class NodeConfigStore {
  static const _key = 'node_config_v1';

  Future<NodeConfig> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.isEmpty) {
      return NodeConfig.defaults();
    }
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    return NodeConfig.fromJson(decoded);
  }

  Future<void> save(NodeConfig config) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(config.toJson()));
  }
}
