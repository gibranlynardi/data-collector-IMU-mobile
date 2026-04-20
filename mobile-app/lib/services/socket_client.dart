import 'dart:async';

import 'package:web_socket_channel/io.dart';

abstract class NodeSocket {
  Stream<dynamic> get stream;
  void send(dynamic data);
  Future<void> close();
}

abstract class NodeSocketClient {
  NodeSocket connect(Uri uri);
}

class IoNodeSocket implements NodeSocket {
  IoNodeSocket(this._channel);

  final IOWebSocketChannel _channel;

  @override
  Stream<dynamic> get stream => _channel.stream;

  @override
  void send(dynamic data) {
    _channel.sink.add(data);
  }

  @override
  Future<void> close() async {
    await _channel.sink.close();
  }
}

class IoNodeSocketClient implements NodeSocketClient {
  @override
  NodeSocket connect(Uri uri) {
    return IoNodeSocket(IOWebSocketChannel.connect(uri));
  }
}
