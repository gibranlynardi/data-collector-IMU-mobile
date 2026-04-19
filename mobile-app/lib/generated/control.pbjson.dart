// This is a generated file - do not edit.
//
// Generated from control.proto.

// @dart = 3.3

// ignore_for_file: annotate_overrides, camel_case_types, comment_references
// ignore_for_file: constant_identifier_names
// ignore_for_file: curly_braces_in_flow_control_structures
// ignore_for_file: deprecated_member_use_from_same_package, library_prefixes
// ignore_for_file: non_constant_identifier_names, prefer_relative_imports
// ignore_for_file: unused_import

import 'dart:convert' as $convert;
import 'dart:core' as $core;
import 'dart:typed_data' as $typed_data;

@$core.Deprecated('Use controlCommandTypeDescriptor instead')
const ControlCommandType$json = {
  '1': 'ControlCommandType',
  '2': [
    {'1': 'CONTROL_COMMAND_TYPE_UNSPECIFIED', '2': 0},
    {'1': 'START_SESSION', '2': 1},
    {'1': 'STOP_SESSION', '2': 2},
    {'1': 'SYNC_CLOCK', '2': 3},
    {'1': 'SYNC_REQUIRED', '2': 4},
    {'1': 'PING', '2': 5},
    {'1': 'ACK', '2': 6},
    {'1': 'CLOCK_SYNC_PONG', '2': 7},
  ],
};

/// Descriptor for `ControlCommandType`. Decode as a `google.protobuf.EnumDescriptorProto`.
final $typed_data.Uint8List controlCommandTypeDescriptor = $convert.base64Decode(
    'ChJDb250cm9sQ29tbWFuZFR5cGUSJAogQ09OVFJPTF9DT01NQU5EX1RZUEVfVU5TUEVDSUZJRU'
    'QQABIRCg1TVEFSVF9TRVNTSU9OEAESEAoMU1RPUF9TRVNTSU9OEAISDgoKU1lOQ19DTE9DSxAD'
    'EhEKDVNZTkNfUkVRVUlSRUQQBBIICgRQSU5HEAUSBwoDQUNLEAYSEwoPQ0xPQ0tfU1lOQ19QT0'
    '5HEAc=');

@$core.Deprecated('Use controlCommandDescriptor instead')
const ControlCommand$json = {
  '1': 'ControlCommand',
  '2': [
    {
      '1': 'command',
      '3': 1,
      '4': 1,
      '5': 14,
      '6': '.imu.collector.v1.ControlCommandType',
      '10': 'command'
    },
    {'1': 'session_id', '3': 2, '4': 1, '5': 9, '10': 'sessionId'},
    {
      '1': 'issued_at_server_unix_ns',
      '3': 3,
      '4': 1,
      '5': 4,
      '10': 'issuedAtServerUnixNs'
    },
    {'1': 'schema_version', '3': 4, '4': 1, '5': 9, '10': 'schemaVersion'},
    {
      '1': 'target_sampling_hz',
      '3': 10,
      '4': 1,
      '5': 13,
      '10': 'targetSamplingHz'
    },
    {
      '1': 'recording_start_seq',
      '3': 11,
      '4': 1,
      '5': 4,
      '10': 'recordingStartSeq'
    },
    {
      '1': 'server_start_time_unix_ns',
      '3': 12,
      '4': 1,
      '5': 4,
      '10': 'serverStartTimeUnixNs'
    },
    {'1': 'backend_last_seq', '3': 13, '4': 1, '5': 4, '10': 'backendLastSeq'},
    {'1': 'command_id', '3': 14, '4': 1, '5': 9, '10': 'commandId'},
    {'1': 'ack', '3': 15, '4': 1, '5': 8, '10': 'ack'},
    {'1': 'device_unix_ns', '3': 16, '4': 1, '5': 4, '10': 'deviceUnixNs'},
    {'1': 'batch_start_seq', '3': 17, '4': 1, '5': 4, '10': 'batchStartSeq'},
    {'1': 'batch_end_seq', '3': 18, '4': 1, '5': 4, '10': 'batchEndSeq'},
    {
      '1': 'duplicate_batches',
      '3': 19,
      '4': 1,
      '5': 4,
      '10': 'duplicateBatches'
    },
    {'1': 'duplicate', '3': 20, '4': 1, '5': 8, '10': 'duplicate'},
    {'1': 'detail', '3': 21, '4': 1, '5': 9, '10': 'detail'},
  ],
};

/// Descriptor for `ControlCommand`. Decode as a `google.protobuf.DescriptorProto`.
final $typed_data.Uint8List controlCommandDescriptor = $convert.base64Decode(
    'Cg5Db250cm9sQ29tbWFuZBI+Cgdjb21tYW5kGAEgASgOMiQuaW11LmNvbGxlY3Rvci52MS5Db2'
    '50cm9sQ29tbWFuZFR5cGVSB2NvbW1hbmQSHQoKc2Vzc2lvbl9pZBgCIAEoCVIJc2Vzc2lvbklk'
    'EjYKGGlzc3VlZF9hdF9zZXJ2ZXJfdW5peF9ucxgDIAEoBFIUaXNzdWVkQXRTZXJ2ZXJVbml4Tn'
    'MSJQoOc2NoZW1hX3ZlcnNpb24YBCABKAlSDXNjaGVtYVZlcnNpb24SLAoSdGFyZ2V0X3NhbXBs'
    'aW5nX2h6GAogASgNUhB0YXJnZXRTYW1wbGluZ0h6Ei4KE3JlY29yZGluZ19zdGFydF9zZXEYCy'
    'ABKARSEXJlY29yZGluZ1N0YXJ0U2VxEjgKGXNlcnZlcl9zdGFydF90aW1lX3VuaXhfbnMYDCAB'
    'KARSFXNlcnZlclN0YXJ0VGltZVVuaXhOcxIoChBiYWNrZW5kX2xhc3Rfc2VxGA0gASgEUg5iYW'
    'NrZW5kTGFzdFNlcRIdCgpjb21tYW5kX2lkGA4gASgJUgljb21tYW5kSWQSEAoDYWNrGA8gASgI'
    'UgNhY2sSJAoOZGV2aWNlX3VuaXhfbnMYECABKARSDGRldmljZVVuaXhOcxImCg9iYXRjaF9zdG'
    'FydF9zZXEYESABKARSDWJhdGNoU3RhcnRTZXESIgoNYmF0Y2hfZW5kX3NlcRgSIAEoBFILYmF0'
    'Y2hFbmRTZXESKwoRZHVwbGljYXRlX2JhdGNoZXMYEyABKARSEGR1cGxpY2F0ZUJhdGNoZXMSHA'
    'oJZHVwbGljYXRlGBQgASgIUglkdXBsaWNhdGUSFgoGZGV0YWlsGBUgASgJUgZkZXRhaWw=');
