// This is a generated file - do not edit.
//
// Generated from sensor_sample.proto.

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

class SensorSample extends $pb.GeneratedMessage {
  factory SensorSample({
    $core.String? sessionId,
    $core.String? deviceId,
    $core.String? deviceRole,
    $fixnum.Int64? seq,
    $fixnum.Int64? timestampDeviceUnixNs,
    $fixnum.Int64? elapsedMs,
    $core.double? accXG,
    $core.double? accYG,
    $core.double? accZG,
    $core.double? gyroXDeg,
    $core.double? gyroYDeg,
    $core.double? gyroZDeg,
  }) {
    final result = create();
    if (sessionId != null) result.sessionId = sessionId;
    if (deviceId != null) result.deviceId = deviceId;
    if (deviceRole != null) result.deviceRole = deviceRole;
    if (seq != null) result.seq = seq;
    if (timestampDeviceUnixNs != null)
      result.timestampDeviceUnixNs = timestampDeviceUnixNs;
    if (elapsedMs != null) result.elapsedMs = elapsedMs;
    if (accXG != null) result.accXG = accXG;
    if (accYG != null) result.accYG = accYG;
    if (accZG != null) result.accZG = accZG;
    if (gyroXDeg != null) result.gyroXDeg = gyroXDeg;
    if (gyroYDeg != null) result.gyroYDeg = gyroYDeg;
    if (gyroZDeg != null) result.gyroZDeg = gyroZDeg;
    return result;
  }

  SensorSample._();

  factory SensorSample.fromBuffer($core.List<$core.int> data,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromBuffer(data, registry);
  factory SensorSample.fromJson($core.String json,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromJson(json, registry);

  static final $pb.BuilderInfo _i = $pb.BuilderInfo(
      _omitMessageNames ? '' : 'SensorSample',
      package:
          const $pb.PackageName(_omitMessageNames ? '' : 'imu.collector.v1'),
      createEmptyInstance: create)
    ..aOS(1, _omitFieldNames ? '' : 'sessionId')
    ..aOS(2, _omitFieldNames ? '' : 'deviceId')
    ..aOS(3, _omitFieldNames ? '' : 'deviceRole')
    ..a<$fixnum.Int64>(4, _omitFieldNames ? '' : 'seq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        5, _omitFieldNames ? '' : 'timestampDeviceUnixNs', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(
        6, _omitFieldNames ? '' : 'elapsedMs', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..aD(7, _omitFieldNames ? '' : 'accXG')
    ..aD(8, _omitFieldNames ? '' : 'accYG')
    ..aD(9, _omitFieldNames ? '' : 'accZG')
    ..aD(10, _omitFieldNames ? '' : 'gyroXDeg')
    ..aD(11, _omitFieldNames ? '' : 'gyroYDeg')
    ..aD(12, _omitFieldNames ? '' : 'gyroZDeg')
    ..hasRequiredFields = false;

  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  SensorSample clone() => deepCopy();
  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  SensorSample copyWith(void Function(SensorSample) updates) =>
      super.copyWith((message) => updates(message as SensorSample))
          as SensorSample;

  @$core.override
  $pb.BuilderInfo get info_ => _i;

  @$core.pragma('dart2js:noInline')
  static SensorSample create() => SensorSample._();
  @$core.override
  SensorSample createEmptyInstance() => create();
  @$core.pragma('dart2js:noInline')
  static SensorSample getDefault() => _defaultInstance ??=
      $pb.GeneratedMessage.$_defaultFor<SensorSample>(create);
  static SensorSample? _defaultInstance;

  @$pb.TagNumber(1)
  $core.String get sessionId => $_getSZ(0);
  @$pb.TagNumber(1)
  set sessionId($core.String value) => $_setString(0, value);
  @$pb.TagNumber(1)
  $core.bool hasSessionId() => $_has(0);
  @$pb.TagNumber(1)
  void clearSessionId() => $_clearField(1);

  @$pb.TagNumber(2)
  $core.String get deviceId => $_getSZ(1);
  @$pb.TagNumber(2)
  set deviceId($core.String value) => $_setString(1, value);
  @$pb.TagNumber(2)
  $core.bool hasDeviceId() => $_has(1);
  @$pb.TagNumber(2)
  void clearDeviceId() => $_clearField(2);

  @$pb.TagNumber(3)
  $core.String get deviceRole => $_getSZ(2);
  @$pb.TagNumber(3)
  set deviceRole($core.String value) => $_setString(2, value);
  @$pb.TagNumber(3)
  $core.bool hasDeviceRole() => $_has(2);
  @$pb.TagNumber(3)
  void clearDeviceRole() => $_clearField(3);

  @$pb.TagNumber(4)
  $fixnum.Int64 get seq => $_getI64(3);
  @$pb.TagNumber(4)
  set seq($fixnum.Int64 value) => $_setInt64(3, value);
  @$pb.TagNumber(4)
  $core.bool hasSeq() => $_has(3);
  @$pb.TagNumber(4)
  void clearSeq() => $_clearField(4);

  @$pb.TagNumber(5)
  $fixnum.Int64 get timestampDeviceUnixNs => $_getI64(4);
  @$pb.TagNumber(5)
  set timestampDeviceUnixNs($fixnum.Int64 value) => $_setInt64(4, value);
  @$pb.TagNumber(5)
  $core.bool hasTimestampDeviceUnixNs() => $_has(4);
  @$pb.TagNumber(5)
  void clearTimestampDeviceUnixNs() => $_clearField(5);

  @$pb.TagNumber(6)
  $fixnum.Int64 get elapsedMs => $_getI64(5);
  @$pb.TagNumber(6)
  set elapsedMs($fixnum.Int64 value) => $_setInt64(5, value);
  @$pb.TagNumber(6)
  $core.bool hasElapsedMs() => $_has(5);
  @$pb.TagNumber(6)
  void clearElapsedMs() => $_clearField(6);

  @$pb.TagNumber(7)
  $core.double get accXG => $_getN(6);
  @$pb.TagNumber(7)
  set accXG($core.double value) => $_setDouble(6, value);
  @$pb.TagNumber(7)
  $core.bool hasAccXG() => $_has(6);
  @$pb.TagNumber(7)
  void clearAccXG() => $_clearField(7);

  @$pb.TagNumber(8)
  $core.double get accYG => $_getN(7);
  @$pb.TagNumber(8)
  set accYG($core.double value) => $_setDouble(7, value);
  @$pb.TagNumber(8)
  $core.bool hasAccYG() => $_has(7);
  @$pb.TagNumber(8)
  void clearAccYG() => $_clearField(8);

  @$pb.TagNumber(9)
  $core.double get accZG => $_getN(8);
  @$pb.TagNumber(9)
  set accZG($core.double value) => $_setDouble(8, value);
  @$pb.TagNumber(9)
  $core.bool hasAccZG() => $_has(8);
  @$pb.TagNumber(9)
  void clearAccZG() => $_clearField(9);

  @$pb.TagNumber(10)
  $core.double get gyroXDeg => $_getN(9);
  @$pb.TagNumber(10)
  set gyroXDeg($core.double value) => $_setDouble(9, value);
  @$pb.TagNumber(10)
  $core.bool hasGyroXDeg() => $_has(9);
  @$pb.TagNumber(10)
  void clearGyroXDeg() => $_clearField(10);

  @$pb.TagNumber(11)
  $core.double get gyroYDeg => $_getN(10);
  @$pb.TagNumber(11)
  set gyroYDeg($core.double value) => $_setDouble(10, value);
  @$pb.TagNumber(11)
  $core.bool hasGyroYDeg() => $_has(10);
  @$pb.TagNumber(11)
  void clearGyroYDeg() => $_clearField(11);

  @$pb.TagNumber(12)
  $core.double get gyroZDeg => $_getN(11);
  @$pb.TagNumber(12)
  set gyroZDeg($core.double value) => $_setDouble(11, value);
  @$pb.TagNumber(12)
  $core.bool hasGyroZDeg() => $_has(11);
  @$pb.TagNumber(12)
  void clearGyroZDeg() => $_clearField(12);
}

class SensorBatch extends $pb.GeneratedMessage {
  factory SensorBatch({
    $core.String? sessionId,
    $core.String? deviceId,
    $fixnum.Int64? startSeq,
    $fixnum.Int64? endSeq,
    $core.Iterable<SensorSample>? samples,
  }) {
    final result = create();
    if (sessionId != null) result.sessionId = sessionId;
    if (deviceId != null) result.deviceId = deviceId;
    if (startSeq != null) result.startSeq = startSeq;
    if (endSeq != null) result.endSeq = endSeq;
    if (samples != null) result.samples.addAll(samples);
    return result;
  }

  SensorBatch._();

  factory SensorBatch.fromBuffer($core.List<$core.int> data,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromBuffer(data, registry);
  factory SensorBatch.fromJson($core.String json,
          [$pb.ExtensionRegistry registry = $pb.ExtensionRegistry.EMPTY]) =>
      create()..mergeFromJson(json, registry);

  static final $pb.BuilderInfo _i = $pb.BuilderInfo(
      _omitMessageNames ? '' : 'SensorBatch',
      package:
          const $pb.PackageName(_omitMessageNames ? '' : 'imu.collector.v1'),
      createEmptyInstance: create)
    ..aOS(1, _omitFieldNames ? '' : 'sessionId')
    ..aOS(2, _omitFieldNames ? '' : 'deviceId')
    ..a<$fixnum.Int64>(
        3, _omitFieldNames ? '' : 'startSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..a<$fixnum.Int64>(4, _omitFieldNames ? '' : 'endSeq', $pb.PbFieldType.OU6,
        defaultOrMaker: $fixnum.Int64.ZERO)
    ..pPM<SensorSample>(5, _omitFieldNames ? '' : 'samples',
        subBuilder: SensorSample.create)
    ..hasRequiredFields = false;

  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  SensorBatch clone() => deepCopy();
  @$core.Deprecated('See https://github.com/google/protobuf.dart/issues/998.')
  SensorBatch copyWith(void Function(SensorBatch) updates) =>
      super.copyWith((message) => updates(message as SensorBatch))
          as SensorBatch;

  @$core.override
  $pb.BuilderInfo get info_ => _i;

  @$core.pragma('dart2js:noInline')
  static SensorBatch create() => SensorBatch._();
  @$core.override
  SensorBatch createEmptyInstance() => create();
  @$core.pragma('dart2js:noInline')
  static SensorBatch getDefault() => _defaultInstance ??=
      $pb.GeneratedMessage.$_defaultFor<SensorBatch>(create);
  static SensorBatch? _defaultInstance;

  @$pb.TagNumber(1)
  $core.String get sessionId => $_getSZ(0);
  @$pb.TagNumber(1)
  set sessionId($core.String value) => $_setString(0, value);
  @$pb.TagNumber(1)
  $core.bool hasSessionId() => $_has(0);
  @$pb.TagNumber(1)
  void clearSessionId() => $_clearField(1);

  @$pb.TagNumber(2)
  $core.String get deviceId => $_getSZ(1);
  @$pb.TagNumber(2)
  set deviceId($core.String value) => $_setString(1, value);
  @$pb.TagNumber(2)
  $core.bool hasDeviceId() => $_has(1);
  @$pb.TagNumber(2)
  void clearDeviceId() => $_clearField(2);

  @$pb.TagNumber(3)
  $fixnum.Int64 get startSeq => $_getI64(2);
  @$pb.TagNumber(3)
  set startSeq($fixnum.Int64 value) => $_setInt64(2, value);
  @$pb.TagNumber(3)
  $core.bool hasStartSeq() => $_has(2);
  @$pb.TagNumber(3)
  void clearStartSeq() => $_clearField(3);

  @$pb.TagNumber(4)
  $fixnum.Int64 get endSeq => $_getI64(3);
  @$pb.TagNumber(4)
  set endSeq($fixnum.Int64 value) => $_setInt64(3, value);
  @$pb.TagNumber(4)
  $core.bool hasEndSeq() => $_has(3);
  @$pb.TagNumber(4)
  void clearEndSeq() => $_clearField(4);

  @$pb.TagNumber(5)
  $pb.PbList<SensorSample> get samples => $_getList(4);
}

const $core.bool _omitFieldNames =
    $core.bool.fromEnvironment('protobuf.omit_field_names');
const $core.bool _omitMessageNames =
    $core.bool.fromEnvironment('protobuf.omit_message_names');
