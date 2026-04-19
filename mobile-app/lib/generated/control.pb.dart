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
    $core.String? commandId,
    $core.bool? ack,
    $fixnum.Int64? deviceUnixNs,
    $fixnum.Int64? batchStartSeq,
    $fixnum.Int64? batchEndSeq,
    $fixnum.Int64? duplicateBatches,
    $core.bool? duplicate,
    $core.String? detail,
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
    if (commandId != null) result.commandId = commandId;
    if (ack != null) result.ack = ack;
    if (deviceUnixNs != null) result.deviceUnixNs = deviceUnixNs;
    if (batchStartSeq != null) result.batchStartSeq = batchStartSeq;
    if (batchEndSeq != null) result.batchEndSeq = batchEndSeq;
    if (duplicateBatches != null) result.duplicateBatches = duplicateBatches;
    if (duplicate != null) result.duplicate = duplicate;
    if (detail != null) result.detail = detail;
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
    ..aOS(14, _omitFieldNames ? '' : 'commandId')
    ..aOB(15, _omitFieldNames ? '' : 'ack')
    ..a<$fixnum.Int64>(
        16, _omitFieldNames ? '' : 'deviceUnixNs', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        17, _omitFieldNames ? '' : 'batchStartSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        18, _omitFieldNames ? '' : 'batchEndSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        19, _omitFieldNames ? '' : 'duplicateBatches', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..aOB(20, _omitFieldNames ? '' : 'duplicate')
    ..aOS(21, _omitFieldNames ? '' : 'detail')
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

  @$pb.TagNumber(14)
  $core.String get commandId => $_getSZ(8);
  @$pb.TagNumber(14)
  set commandId($core.String value) => $_setString(8, value);
  @$pb.TagNumber(14)
  $core.bool hasCommandId() => $_has(8);
  @$pb.TagNumber(14)
  void clearCommandId() => $_clearField(14);

  @$pb.TagNumber(15)
  $core.bool get ack => $_getBF(9);
  @$pb.TagNumber(15)
  set ack($core.bool value) => $_setBool(9, value);
  @$pb.TagNumber(15)
  $core.bool hasAck() => $_has(9);
  @$pb.TagNumber(15)
  void clearAck() => $_clearField(15);

  @$pb.TagNumber(16)
  $fixnum.Int64 get deviceUnixNs => $_getI64(10);
  @$pb.TagNumber(16)
  set deviceUnixNs($fixnum.Int64 value) => $_setInt64(10, value);
  @$pb.TagNumber(16)
  $core.bool hasDeviceUnixNs() => $_has(10);
  @$pb.TagNumber(16)
  void clearDeviceUnixNs() => $_clearField(16);

  @$pb.TagNumber(17)
  $fixnum.Int64 get batchStartSeq => $_getI64(11);
  @$pb.TagNumber(17)
  set batchStartSeq($fixnum.Int64 value) => $_setInt64(11, value);
  @$pb.TagNumber(17)
  $core.bool hasBatchStartSeq() => $_has(11);
  @$pb.TagNumber(17)
  void clearBatchStartSeq() => $_clearField(17);

  @$pb.TagNumber(18)
  $fixnum.Int64 get batchEndSeq => $_getI64(12);
  @$pb.TagNumber(18)
  set batchEndSeq($fixnum.Int64 value) => $_setInt64(12, value);
  @$pb.TagNumber(18)
  $core.bool hasBatchEndSeq() => $_has(12);
  @$pb.TagNumber(18)
  void clearBatchEndSeq() => $_clearField(18);

  @$pb.TagNumber(19)
  $fixnum.Int64 get duplicateBatches => $_getI64(13);
  @$pb.TagNumber(19)
  set duplicateBatches($fixnum.Int64 value) => $_setInt64(13, value);
  @$pb.TagNumber(19)
  $core.bool hasDuplicateBatches() => $_has(13);
  @$pb.TagNumber(19)
  void clearDuplicateBatches() => $_clearField(19);

  @$pb.TagNumber(20)
  $core.bool get duplicate => $_getBF(14);
  @$pb.TagNumber(20)
  set duplicate($core.bool value) => $_setBool(14, value);
  @$pb.TagNumber(20)
  $core.bool hasDuplicate() => $_has(14);
  @$pb.TagNumber(20)
  void clearDuplicate() => $_clearField(20);

  @$pb.TagNumber(21)
  $core.String get detail => $_getSZ(15);
  @$pb.TagNumber(21)
  set detail($core.String value) => $_setString(15, value);
  @$pb.TagNumber(21)
  $core.bool hasDetail() => $_has(15);
  @$pb.TagNumber(21)
  void clearDetail() => $_clearField(21);
}

const $core.bool _omitFieldNames =
    $core.bool.fromEnvironment('protobuf.omit_field_names');
const $core.bool _omitMessageNames =
    $core.bool.fromEnvironment('protobuf.omit_message_names');
