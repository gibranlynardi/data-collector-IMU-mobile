// This is a generated file - do not edit.
//
// Generated from device_status.proto.

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

@$core.Deprecated('Use deviceStatusDescriptor instead')
const DeviceStatus$json = {
  '1': 'DeviceStatus',
  '2': [
    {'1': 'device_id', '3': 1, '4': 1, '5': 9, '10': 'deviceId'},
    {'1': 'device_role', '3': 2, '4': 1, '5': 9, '10': 'deviceRole'},
    {'1': 'connected', '3': 3, '4': 1, '5': 8, '10': 'connected'},
    {'1': 'recording', '3': 4, '4': 1, '5': 8, '10': 'recording'},
    {'1': 'local_last_seq', '3': 5, '4': 1, '5': 4, '10': 'localLastSeq'},
    {
      '1': 'backend_last_ack_seq',
      '3': 6,
      '4': 1,
      '5': 4,
      '10': 'backendLastAckSeq'
    },
    {'1': 'pending_samples', '3': 7, '4': 1, '5': 13, '10': 'pendingSamples'},
    {'1': 'battery_percent', '3': 8, '4': 1, '5': 2, '10': 'batteryPercent'},
    {'1': 'storage_free_mb', '3': 9, '4': 1, '5': 13, '10': 'storageFreeMb'},
    {'1': 'effective_hz', '3': 10, '4': 1, '5': 2, '10': 'effectiveHz'},
  ],
};

/// Descriptor for `DeviceStatus`. Decode as a `google.protobuf.DescriptorProto`.
final $typed_data.Uint8List deviceStatusDescriptor = $convert.base64Decode(
    'CgxEZXZpY2VTdGF0dXMSGwoJZGV2aWNlX2lkGAEgASgJUghkZXZpY2VJZBIfCgtkZXZpY2Vfcm'
    '9sZRgCIAEoCVIKZGV2aWNlUm9sZRIcCgljb25uZWN0ZWQYAyABKAhSCWNvbm5lY3RlZBIcCgly'
    'ZWNvcmRpbmcYBCABKAhSCXJlY29yZGluZxIkCg5sb2NhbF9sYXN0X3NlcRgFIAEoBFIMbG9jYW'
    'xMYXN0U2VxEi8KFGJhY2tlbmRfbGFzdF9hY2tfc2VxGAYgASgEUhFiYWNrZW5kTGFzdEFja1Nl'
    'cRInCg9wZW5kaW5nX3NhbXBsZXMYByABKA1SDnBlbmRpbmdTYW1wbGVzEicKD2JhdHRlcnlfcG'
    'VyY2VudBgIIAEoAlIOYmF0dGVyeVBlcmNlbnQSJgoPc3RvcmFnZV9mcmVlX21iGAkgASgNUg1z'
    'dG9yYWdlRnJlZU1iEiEKDGVmZmVjdGl2ZV9oehgKIAEoAlILZWZmZWN0aXZlSHo=');
