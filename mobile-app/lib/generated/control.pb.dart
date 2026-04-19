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

import 'package:fixnum/fixnum.dart' as $fixnum;
import 'package:protobuf/protobuf.dart' as $pb;

import 'control.pbenum.dart';

export 'package:protobuf/protobuf.dart' show GeneratedMessageGenericExtensions;

export 'control.pbenum.dart';

class ControlCommand extends $pb.GeneratedMessage {
  factory ControlCommand({
    ControlCommandType? command,
    $core.String? sessionId,
    $fixnum.Int64? issuedAtServerUnixNs,
    $core.String? schemaVersion,
    $core.int? targetSamplingHz,
    $fixnum.Int64? recordingStartSeq,
    $fixnum.Int64? serverStartTimeUnixNs,
    $fixnum.Int64? backendLastSeq,
  }) {
    final result = create();
    if (command != null) result.command = command;
    if (sessionId != null) result.sessionId = sessionId;
    if (issuedAtServerUnixNs != null)
      result.issuedAtServerUnixNs = issuedAtServerUnixNs;
    if (schemaVersion != null) result.schemaVersion = schemaVersion;
    if (targetSamplingHz != null) result.targetSamplingHz = targetSamplingHz;
    if (recordingStartSeq != null) result.recordingStartSeq = recordingStartSeq;
    if (serverStartTimeUnixNs != null)
      result.serverStartTimeUnixNs = serverStartTimeUnixNs;
    if (backendLastSeq != null) result.backendLastSeq = backendLastSeq;
    return result;
  }

  ControlCommand._();

  factory ControlCommand.fromBuffer($core.List<$core.int> data,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromBuffer(data, registry);
  factory ControlCommand.fromJson($core.String json,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromJson(json, registry);

  static final $pb.BuilderInfo _i = $pb.BuilderInfo(
      _omitMessageNames ? '' : 'ControlCommand',
      package:
          const $pb.PackageName(_omitMessageNames ? '' : 'imu.collector.v1'),
      createEmptyInstance: create)
    ..aE<ControlCommandType>(1, _omitFieldNames ? '' : 'command',
        enumValues: ControlCommandType.values)
    ..aOS(2, _omitFieldNames ? '' : 'sessionId')
    ..a<$fixnum.Int64>(
        3, _omitFieldNames ? '' : 'issuedAtServerUnixNs', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..aOS(4, _omitFieldNames ? '' : 'schemaVersion')
    ..aI(10, _omitFieldNames ? '' : 'targetSamplingHz',
        fieldType: $pb.PbFieldType.OU3)
    ..a<$fixnum.Int64>(
        11, _omitFieldNames ? '' : 'recordingStartSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        12, _omitFieldNames ? '' : 'serverStartTimeUnixNs', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        13, _omitFieldNames ? '' : 'backendLastSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..hasRequiredFields = false;

  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  ControlCommand clone() => deepCopy();
  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  ControlCommand copyWith(void Function(ControlCommand) updates) =>
      super.copyWith((message) => updates(message as ControlCommand))
          as ControlCommand;

  @$core.override
  $pb.BuilderInfo get info_ => _i;

  @$core.pragma('dart2js:noInline')
  static ControlCommand create() => ControlCommand._();
  @$core.override
  ControlCommand createEmptyInstance() => create();
  @$core.pragma('dart2js:noInline')
  static ControlCommand getDefault() => _defaultInstance ??=
      $pb.GeneratedMessage.$_defaultFor<ControlCommand>(create);
  static ControlCommand? _defaultInstance;

  @$pb.TagNumber(1)
  ControlCommandType get command => $_getN(0);
  @$pb.TagNumber(1)
  set command(ControlCommandType value) => $_setField(1, value);
  @$pb.TagNumber(1)
  $core.bool hasCommand() => $_has(0);
  @$pb.TagNumber(1)
  void clearCommand() => $_clearField(1);

  @$pb.TagNumber(2)
  $core.String get sessionId => $_getSZ(1);
  @$pb.TagNumber(2)
  set sessionId($core.String value) => $_setString(1, value);
  @$pb.TagNumber(2)
  $core.bool hasSessionId() => $_has(1);
  @$pb.TagNumber(2)
  void clearSessionId() => $_clearField(2);

  @$pb.TagNumber(3)
  $fixnum.Int64 get issuedAtServerUnixNs => $_getI64(2);
  @$pb.TagNumber(3)
  set issuedAtServerUnixNs($fixnum.Int64 value) => $_setInt64(2, value);
  @$pb.TagNumber(3)
  $core.bool hasIssuedAtServerUnixNs() => $_has(2);
  @$pb.TagNumber(3)
  void clearIssuedAtServerUnixNs() => $_clearField(3);

  @$pb.TagNumber(4)
  $core.String get schemaVersion => $_getSZ(3);
  @$pb.TagNumber(4)
  set schemaVersion($core.String value) => $_setString(3, value);
  @$pb.TagNumber(4)
  $core.bool hasSchemaVersion() => $_has(3);
  @$pb.TagNumber(4)
  void clearSchemaVersion() => $_clearField(4);

  /// Optional command arguments.
  @$pb.TagNumber(10)
  $core.int get targetSamplingHz => $_getIZ(4);
  @$pb.TagNumber(10)
  set targetSamplingHz($core.int value) => $_setUnsignedInt32(4, value);
  @$pb.TagNumber(10)
  $core.bool hasTargetSamplingHz() => $_has(4);
  @$pb.TagNumber(10)
  void clearTargetSamplingHz() => $_clearField(10);

  @$pb.TagNumber(11)
  $fixnum.Int64 get recordingStartSeq => $_getI64(5);
  @$pb.TagNumber(11)
  set recordingStartSeq($fixnum.Int64 value) => $_setInt64(5, value);
  @$pb.TagNumber(11)
  $core.bool hasRecordingStartSeq() => $_has(5);
  @$pb.TagNumber(11)
  void clearRecordingStartSeq() => $_clearField(11);

  @$pb.TagNumber(12)
  $fixnum.Int64 get serverStartTimeUnixNs => $_getI64(6);
  @$pb.TagNumber(12)
  set serverStartTimeUnixNs($fixnum.Int64 value) => $_setInt64(6, value);
  @$pb.TagNumber(12)
  $core.bool hasServerStartTimeUnixNs() => $_has(6);
  @$pb.TagNumber(12)
  void clearServerStartTimeUnixNs() => $_clearField(12);

  @$pb.TagNumber(13)
  $fixnum.Int64 get backendLastSeq => $_getI64(7);
  @$pb.TagNumber(13)
  set backendLastSeq($fixnum.Int64 value) => $_setInt64(7, value);
  @$pb.TagNumber(13)
  $core.bool hasBackendLastSeq() => $_has(7);
  @$pb.TagNumber(13)
  void clearBackendLastSeq() => $_clearField(13);
}

const $core.bool _omitFieldNames =
    $core.bool.fromEnvironment('protobuf.omit_field_names');
const $core.bool _omitMessageNames =
    $core.bool.fromEnvironment('protobuf.omit_message_names');
