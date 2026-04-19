// This is a generated file - do not edit.
//
// Generated from device_status.proto.

// @dart = 3.3

// ignore_for_file: annotate_overrides, camel_case_types, comment_references
// ignore_for_file: constant_identifier_names
// ignore_for_file: curly_braces_in_flow_control_structures
// ignore_for_file: deprecated_member_use_from_same_package, library_prefixes
// ignore_for_file: non_constant_identifier_names, prefer_relative_imports

import 'dart:core' as $core;

import 'package:fixnum/fixnum.dart' as $fixnum;
import 'package:protobuf/protobuf.dart' as $pb;

export 'package:protobuf/protobuf.dart' show GeneratedMessageGenericExtensions;

class DeviceStatus extends $pb.GeneratedMessage {
  factory DeviceStatus({
    $core.String? deviceId,
    $core.String? deviceRole,
    $core.bool? connected,
    $core.bool? recording,
    $fixnum.Int64? localLastSeq,
    $fixnum.Int64? backendLastAckSeq,
    $core.int? pendingSamples,
    $core.double? batteryPercent,
    $core.int? storageFreeMb,
    $core.double? effectiveHz,
  }) {
    final result = create();
    if (deviceId != null) result.deviceId = deviceId;
    if (deviceRole != null) result.deviceRole = deviceRole;
    if (connected != null) result.connected = connected;
    if (recording != null) result.recording = recording;
    if (localLastSeq != null) result.localLastSeq = localLastSeq;
    if (backendLastAckSeq != null) result.backendLastAckSeq = backendLastAckSeq;
    if (pendingSamples != null) result.pendingSamples = pendingSamples;
    if (batteryPercent != null) result.batteryPercent = batteryPercent;
    if (storageFreeMb != null) result.storageFreeMb = storageFreeMb;
    if (effectiveHz != null) result.effectiveHz = effectiveHz;
    return result;
  }

  DeviceStatus._();

  factory DeviceStatus.fromBuffer($core.List<$core.int> data,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromBuffer(data, registry);
  factory DeviceStatus.fromJson($core.String json,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromJson(json, registry);

  static final $pb.BuilderInfo _i = $pb.BuilderInfo(
      _omitMessageNames ? '' : 'DeviceStatus',
      package:
          const $pb.PackageName(_omitMessageNames ? '' : 'imu.collector.v1'),
      createEmptyInstance: create)
    ..aOS(1, _omitFieldNames ? '' : 'deviceId')
    ..aOS(2, _omitFieldNames ? '' : 'deviceRole')
    ..aOB(3, _omitFieldNames ? '' : 'connected')
    ..aOB(4, _omitFieldNames ? '' : 'recording')
    ..a<$fixnum.Int64>(
        5, _omitFieldNames ? '' : 'localLastSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        6, _omitFieldNames ? '' : 'backendLastAckSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..aI(7, _omitFieldNames ? '' : 'pendingSamples',
        fieldType: $pb.PbFieldType.OU3)
    ..aD(8, _omitFieldNames ? '' : 'batteryPercent',
        fieldType: $pb.PbFieldType.OF)
    ..aI(9, _omitFieldNames ? '' : 'storageFreeMb',
        fieldType: $pb.PbFieldType.OU3)
    ..aD(10, _omitFieldNames ? '' : 'effectiveHz',
        fieldType: $pb.PbFieldType.OF)
    ..hasRequiredFields = false;

  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  DeviceStatus clone() => deepCopy();
  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  DeviceStatus copyWith(void Function(DeviceStatus) updates) =>
      super.copyWith((message) => updates(message as DeviceStatus))
          as DeviceStatus;

  @$core.override
  $pb.BuilderInfo get info_ => _i;

  @$core.pragma('dart2js:noInline')
  static DeviceStatus create() => DeviceStatus._();
  @$core.override
  DeviceStatus createEmptyInstance() => create();
  @$core.pragma('dart2js:noInline')
  static DeviceStatus getDefault() => _defaultInstance ??=
      $pb.GeneratedMessage.$_defaultFor<DeviceStatus>(create);
  static DeviceStatus? _defaultInstance;

  @$pb.TagNumber(1)
  $core.String get deviceId => $_getSZ(0);
  @$pb.TagNumber(1)
  set deviceId($core.String value) => $_setString(0, value);
  @$pb.TagNumber(1)
  $core.bool hasDeviceId() => $_has(0);
  @$pb.TagNumber(1)
  void clearDeviceId() => $_clearField(1);

  @$pb.TagNumber(2)
  $core.String get deviceRole => $_getSZ(1);
  @$pb.TagNumber(2)
  set deviceRole($core.String value) => $_setString(1, value);
  @$pb.TagNumber(2)
  $core.bool hasDeviceRole() => $_has(1);
  @$pb.TagNumber(2)
  void clearDeviceRole() => $_clearField(2);

  @$pb.TagNumber(3)
  $core.bool get connected => $_getBF(2);
  @$pb.TagNumber(3)
  set connected($core.bool value) => $_setBool(2, value);
  @$pb.TagNumber(3)
  $core.bool hasConnected() => $_has(2);
  @$pb.TagNumber(3)
  void clearConnected() => $_clearField(3);

  @$pb.TagNumber(4)
  $core.bool get recording => $_getBF(3);
  @$pb.TagNumber(4)
  set recording($core.bool value) => $_setBool(3, value);
  @$pb.TagNumber(4)
  $core.bool hasRecording() => $_has(3);
  @$pb.TagNumber(4)
  void clearRecording() => $_clearField(4);

  @$pb.TagNumber(5)
  $fixnum.Int64 get localLastSeq => $_getI64(4);
  @$pb.TagNumber(5)
  set localLastSeq($fixnum.Int64 value) => $_setInt64(4, value);
  @$pb.TagNumber(5)
  $core.bool hasLocalLastSeq() => $_has(4);
  @$pb.TagNumber(5)
  void clearLocalLastSeq() => $_clearField(5);

  @$pb.TagNumber(6)
  $fixnum.Int64 get backendLastAckSeq => $_getI64(5);
  @$pb.TagNumber(6)
  set backendLastAckSeq($fixnum.Int64 value) => $_setInt64(5, value);
  @$pb.TagNumber(6)
  $core.bool hasBackendLastAckSeq() => $_has(5);
  @$pb.TagNumber(6)
  void clearBackendLastAckSeq() => $_clearField(6);

  @$pb.TagNumber(7)
  $core.int get pendingSamples => $_getIZ(6);
  @$pb.TagNumber(7)
  set pendingSamples($core.int value) => $_setUnsignedInt32(6, value);
  @$pb.TagNumber(7)
  $core.bool hasPendingSamples() => $_has(6);
  @$pb.TagNumber(7)
  void clearPendingSamples() => $_clearField(7);

  @$pb.TagNumber(8)
  $core.double get batteryPercent => $_getN(7);
  @$pb.TagNumber(8)
  set batteryPercent($core.double value) => $_setFloat(7, value);
  @$pb.TagNumber(8)
  $core.bool hasBatteryPercent() => $_has(7);
  @$pb.TagNumber(8)
  void clearBatteryPercent() => $_clearField(8);

  @$pb.TagNumber(9)
  $core.int get storageFreeMb => $_getIZ(8);
  @$pb.TagNumber(9)
  set storageFreeMb($core.int value) => $_setUnsignedInt32(8, value);
  @$pb.TagNumber(9)
  $core.bool hasStorageFreeMb() => $_has(8);
  @$pb.TagNumber(9)
  void clearStorageFreeMb() => $_clearField(9);

  @$pb.TagNumber(10)
  $core.double get effectiveHz => $_getN(9);
  @$pb.TagNumber(10)
  set effectiveHz($core.double value) => $_setFloat(9, value);
  @$pb.TagNumber(10)
  $core.bool hasEffectiveHz() => $_has(9);
  @$pb.TagNumber(10)
  void clearEffectiveHz() => $_clearField(10);
}

const $core.bool _omitFieldNames =
    $core.bool.fromEnvironment('protobuf.omit_field_names');
const $core.bool _omitMessageNames =
    $core.bool.fromEnvironment('protobuf.omit_message_names');
