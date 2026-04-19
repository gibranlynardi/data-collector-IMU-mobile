// This is a generated file - do not edit.
//
// Generated from sensor_sample.proto.

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

@$core.Deprecated('Use sensorSampleDescriptor instead')
const SensorSample$json = {
  '1': 'SensorSample',
  '2': [
    {'1': 'session_id', '3': 1, '4': 1, '5': 9, '10': 'sessionId'},
    {'1': 'device_id', '3': 2, '4': 1, '5': 9, '10': 'deviceId'},
    {'1': 'device_role', '3': 3, '4': 1, '5': 9, '10': 'deviceRole'},
    {'1': 'seq', '3': 4, '4': 1, '5': 4, '10': 'seq'},
    {
      '1': 'timestamp_device_unix_ns',
      '3': 5,
      '4': 1,
      '5': 4,
      '10': 'timestampDeviceUnixNs'
    },
    {'1': 'elapsed_ms', '3': 6, '4': 1, '5': 4, '10': 'elapsedMs'},
    {'1': 'acc_x_g', '3': 7, '4': 1, '5': 1, '10': 'accXG'},
    {'1': 'acc_y_g', '3': 8, '4': 1, '5': 1, '10': 'accYG'},
    {'1': 'acc_z_g', '3': 9, '4': 1, '5': 1, '10': 'accZG'},
    {'1': 'gyro_x_deg', '3': 10, '4': 1, '5': 1, '10': 'gyroXDeg'},
    {'1': 'gyro_y_deg', '3': 11, '4': 1, '5': 1, '10': 'gyroYDeg'},
    {'1': 'gyro_z_deg', '3': 12, '4': 1, '5': 1, '10': 'gyroZDeg'},
  ],
};

/// Descriptor for `SensorSample`. Decode as a `google.protobuf.DescriptorProto`.
final $typed_data.Uint8List sensorSampleDescriptor = $convert.base64Decode(
    'CgxTZW5zb3JTYW1wbGUSHQoKc2Vzc2lvbl9pZBgBIAEoCVIJc2Vzc2lvbklkEhsKCWRldmljZV'
    '9pZBgCIAEoCVIIZGV2aWNlSWQSHwoLZGV2aWNlX3JvbGUYAyABKAlSCmRldmljZVJvbGUSEAoD'
    'c2VxGAQgASgEUgNzZXESNwoYdGltZXN0YW1wX2RldmljZV91bml4X25zGAUgASgEUhV0aW1lc3'
    'RhbXBEZXZpY2VVbml4TnMSHQoKZWxhcHNlZF9tcxgGIAEoBFIJZWxhcHNlZE1zEhYKB2FjY194'
    'X2cYByABKAFSBWFjY1hHEhYKB2FjY195X2cYCCABKAFSBWFjY1lHEhYKB2FjY196X2cYCSABKA'
    'FSBWFjY1pHEhwKCmd5cm9feF9kZWcYCiABKAFSCGd5cm9YRGVnEhwKCmd5cm9feV9kZWcYCyAB'
    'KAFSCGd5cm9ZRGVnEhwKCmd5cm9fel9kZWcYDCABKAFSCGd5cm9aRGVn');

@$core.Deprecated('Use sensorBatchDescriptor instead')
const SensorBatch$json = {
  '1': 'SensorBatch',
  '2': [
    {'1': 'session_id', '3': 1, '4': 1, '5': 9, '10': 'sessionId'},
    {'1': 'device_id', '3': 2, '4': 1, '5': 9, '10': 'deviceId'},
    {'1': 'start_seq', '3': 3, '4': 1, '5': 4, '10': 'startSeq'},
    {'1': 'end_seq', '3': 4, '4': 1, '5': 4, '10': 'endSeq'},
    {
      '1': 'samples',
      '3': 5,
      '4': 3,
      '5': 11,
      '6': '.imu.collector.v1.SensorSample',
      '10': 'samples'
    },
  ],
};

/// Descriptor for `SensorBatch`. Decode as a `google.protobuf.DescriptorProto`.
final $typed_data.Uint8List sensorBatchDescriptor = $convert.base64Decode(
    'CgtTZW5zb3JCYXRjaBIdCgpzZXNzaW9uX2lkGAEgASgJUglzZXNzaW9uSWQSGwoJZGV2aWNlX2'
    'lkGAIgASgJUghkZXZpY2VJZBIbCglzdGFydF9zZXEYAyABKARSCHN0YXJ0U2VxEhcKB2VuZF9z'
    'ZXEYBCABKARSBmVuZFNlcRI4CgdzYW1wbGVzGAUgAygLMh4uaW11LmNvbGxlY3Rvci52MS5TZW'
    '5zb3JTYW1wbGVSB3NhbXBsZXM=');
