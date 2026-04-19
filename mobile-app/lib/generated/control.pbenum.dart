// This is a generated file - do not edit.
//
// Generated from control.proto.

// @dart = 3.3

// ignore_for_file: annotate_overrides, camel_case_types, comment_references
// ignore_for_file: constant_identifier_names
// ignore_for_file: curly_braces_in_flow_control_structures
// ignore_for_file: deprecated_member_use_from_same_package, library_prefixes
// ignore_for_file: non_constant_identifier_names, prefer_relative_imports

import 'dart:core' as $core;

import 'package:protobuf/protobuf.dart' as $pb;

class ControlCommandType extends $pb.ProtobufEnum {
  static const ControlCommandType CONTROL_COMMAND_TYPE_UNSPECIFIED =
      ControlCommandType._(
          0, _omitEnumNames ? '' : 'CONTROL_COMMAND_TYPE_UNSPECIFIED');
  static const ControlCommandType START_SESSION =
      ControlCommandType._(1, _omitEnumNames ? '' : 'START_SESSION');
  static const ControlCommandType STOP_SESSION =
      ControlCommandType._(2, _omitEnumNames ? '' : 'STOP_SESSION');
  static const ControlCommandType SYNC_CLOCK =
      ControlCommandType._(3, _omitEnumNames ? '' : 'SYNC_CLOCK');
  static const ControlCommandType SYNC_REQUIRED =
      ControlCommandType._(4, _omitEnumNames ? '' : 'SYNC_REQUIRED');
  static const ControlCommandType PING =
      ControlCommandType._(5, _omitEnumNames ? '' : 'PING');
  static const ControlCommandType ACK =
      ControlCommandType._(6, _omitEnumNames ? '' : 'ACK');
  static const ControlCommandType CLOCK_SYNC_PONG =
      ControlCommandType._(7, _omitEnumNames ? '' : 'CLOCK_SYNC_PONG');

  static const $core.List<ControlCommandType> values = <ControlCommandType>[
    CONTROL_COMMAND_TYPE_UNSPECIFIED,
    START_SESSION,
    STOP_SESSION,
    SYNC_CLOCK,
    SYNC_REQUIRED,
    PING,
    ACK,
    CLOCK_SYNC_PONG,
  ];

  static final $core.List<ControlCommandType?> _byValue =
      $pb.ProtobufEnum.$_initByValueList(values, 7);
  static ControlCommandType? valueOf($core.int value) =>
      value < 0 || value >= _byValue.length ? null : _byValue[value];

  const ControlCommandType._(super.value, super.name);
}

const $core.bool _omitEnumNames =
    $core.bool.fromEnvironment('protobuf.omit_enum_names');
