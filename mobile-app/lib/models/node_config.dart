class NodeConfig {
  const NodeConfig({
    required this.backendBaseUrl,
    required this.wsPort,
    required this.deviceId,
    required this.deviceRole,
    required this.displayName,
    required this.sessionId,
  });

  final String backendBaseUrl;
  final int wsPort;
  final String deviceId;
  final String deviceRole;
  final String displayName;
  final String sessionId;

  NodeConfig copyWith({
    String? backendBaseUrl,
    int? wsPort,
    String? deviceId,
    String? deviceRole,
    String? displayName,
    String? sessionId,
  }) {
    return NodeConfig(
      backendBaseUrl: backendBaseUrl ?? this.backendBaseUrl,
      wsPort: wsPort ?? this.wsPort,
      deviceId: deviceId ?? this.deviceId,
      deviceRole: deviceRole ?? this.deviceRole,
      displayName: displayName ?? this.displayName,
      sessionId: sessionId ?? this.sessionId,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'backendBaseUrl': backendBaseUrl,
      'wsPort': wsPort,
      'deviceId': deviceId,
      'deviceRole': deviceRole,
      'displayName': displayName,
      'sessionId': sessionId,
    };
  }

  static NodeConfig fromJson(Map<String, dynamic> json) {
    return NodeConfig(
      backendBaseUrl: (json['backendBaseUrl'] as String? ?? 'http://127.0.0.1:8000').trim(),
      wsPort: (json['wsPort'] as int? ?? 8000),
      deviceId: (json['deviceId'] as String? ?? 'DEVICE-OTHER-001').trim().toUpperCase(),
      deviceRole: (json['deviceRole'] as String? ?? 'other').trim().toLowerCase(),
      displayName: (json['displayName'] as String? ?? 'IMU Mobile Node').trim(),
      sessionId: (json['sessionId'] as String? ?? '').trim().toUpperCase(),
    );
  }

  static NodeConfig defaults() {
    return const NodeConfig(
      backendBaseUrl: 'http://127.0.0.1:8000',
      wsPort: 8000,
      deviceId: 'DEVICE-OTHER-001',
      deviceRole: 'other',
      displayName: 'IMU Mobile Node',
      sessionId: '',
    );
  }
}
