// Hand-written protobuf serializer matching shared_contracts/commands.proto.
// Replace with protoc-generated output after running `make proto-dart`.
import 'dart:convert';
import 'dart:typed_data';

// ignore_for_file: non_constant_identifier_names

abstract class CommandType {
  static const int PING = 0;
  static const int PONG = 1;
  static const int START_SESSION = 2;
  static const int STOP_SESSION = 3;
  static const int SET_LABEL = 4;
  static const int ACK = 5;
  static const int CLOCK_SYNC = 6;
  static const int ERROR_ALERT = 7;
}

class CommandProto {
  int type;
  String payload;
  int issuedAtMs;
  String commandId;

  CommandProto({
    this.type = CommandType.PING,
    this.payload = '',
    this.issuedAtMs = 0,
    this.commandId = '',
  });

  Uint8List toBytes() {
    final w = _ProtoWriter();
    w.writeVarint(1, type);
    w.writeString(2, payload);
    w.writeInt64(3, issuedAtMs);
    w.writeString(4, commandId);
    return w.build();
  }

  static CommandProto fromBytes(Uint8List bytes) {
    final cmd = CommandProto();
    int pos = 0;
    while (pos < bytes.length) {
      final tagByte = _readVarint(bytes, pos);
      pos = tagByte.$2;
      final fieldNumber = tagByte.$1 >> 3;
      final wireType = tagByte.$1 & 0x7;

      switch (wireType) {
        case 0: // varint
          final val = _readVarint(bytes, pos);
          pos = val.$2;
          if (fieldNumber == 1) cmd.type = val.$1;
          if (fieldNumber == 3) cmd.issuedAtMs = val.$1;
        case 2: // length-delimited
          final lenR = _readVarint(bytes, pos);
          pos = lenR.$2;
          final end = pos + lenR.$1;
          final chunk = bytes.sublist(pos, end);
          pos = end;
          if (fieldNumber == 2) cmd.payload = utf8.decode(chunk);
          if (fieldNumber == 4) cmd.commandId = utf8.decode(chunk);
        default:
          pos = bytes.length; // skip unknown
      }
    }
    return cmd;
  }

  static (int, int) _readVarint(Uint8List bytes, int pos) {
    int result = 0;
    int shift = 0;
    while (pos < bytes.length) {
      final b = bytes[pos++];
      result |= (b & 0x7F) << shift;
      if ((b & 0x80) == 0) break;
      shift += 7;
    }
    return (result, pos);
  }
}

class _ProtoWriter {
  final List<int> _buf = [];

  void writeVarint(int field, int value) {
    _tag(field, 0);
    _varint(value);
  }

  void writeInt64(int field, int value) {
    _tag(field, 0);
    _varint(value);
  }

  void writeString(int field, String value) {
    if (value.isEmpty) return;
    final encoded = utf8.encode(value);
    _tag(field, 2);
    _varint(encoded.length);
    _buf.addAll(encoded);
  }

  void _tag(int field, int wireType) => _varint((field << 3) | wireType);

  void _varint(int v) {
    while (v >>> 7 != 0) {
      _buf.add((v & 0x7F) | 0x80);
      v = v >>> 7;
    }
    _buf.add(v & 0x7F);
  }

  Uint8List build() => Uint8List.fromList(_buf);
}
