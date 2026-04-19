export type HealthResponse = {
  status: string;
  rest_port: number;
  ws_port: number;
};

export type PreflightResponse = {
  backend_healthy: boolean;
  storage_path_writable: boolean;
  storage_free_bytes: number;
  webcam_connected: boolean;
  webcam_preview_ok: boolean;
  webcam_fps: number;
  webcam_fps_ok: boolean;
  webcam_storage_ok: boolean;
  webcam_available: boolean;
  webcam_detail: string;
};

export type SessionResponse = {
  session_id: string;
  status: string;
  preflight_passed: boolean;
  override_reason: string | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
  finalized_at: string | null;
};

export type DeviceResponse = {
  device_id: string;
  device_role: string;
  display_name: string | null;
  ip_address: string | null;
  connected: boolean;
  recording: boolean;
  battery_percent: number | null;
  storage_free_mb: number | null;
  effective_hz: number | null;
  created_at: string;
  updated_at: string;
};

export type SessionBinding = {
  device_id: string;
  device_role: string;
  required: boolean;
  connected: boolean;
};

export type SessionDeviceAssignmentResponse = {
  session_id: string;
  required_roles: string[];
  bindings: SessionBinding[];
};

export type SessionDeviceAssignItem = {
  device_id: string;
  required: boolean;
};

export type AnnotationResponse = {
  annotation_id: string;
  session_id: string;
  label: string;
  notes: string | null;
  started_at: string;
  ended_at: string | null;
  auto_closed: boolean;
  deleted: boolean;
};

export type ArtifactResponse = {
  id: number;
  session_id: string;
  artifact_type: string;
  file_path: string;
  exists: boolean;
  size_bytes: number | null;
  checksum: string | null;
  created_at: string;
};

export type VideoStatusResponse = {
  status: string;
  session_id: string;
  video_id: string | null;
  camera_id: string | null;
  file_path: string | null;
  backend: string | null;
  elapsed_ms: number;
  frame_count: number;
  dropped_frame_estimate: number;
};

export type VideoMetadataResponse = {
  session_id: string;
  camera_id: string;
  fps: number;
  width: number;
  height: number;
  codec: string;
  video_start_server_time: string;
  video_start_monotonic_ms: number | null;
  video_end_server_time: string;
  video_end_monotonic_ms: number | null;
  duration_ms: number;
  frame_count: number;
  dropped_frame_estimate: number;
  file_path: string;
  status: string;
  error: string | null;
  backend: string | null;
};

export type VideoAnonymizeResponse = {
  session_id: string;
  status: string;
  source_file_path: string;
  output_file_path: string | null;
  metadata_file_path: string | null;
  frame_count: number;
  faces_blurred: number;
  error: string | null;
};

export type SyncDeviceReport = {
  device_id: string;
  probes_ok: number;
  probes_total: number;
  clock_offset_ms: number | null;
  latency_ms_min: number | null;
  latency_ms_median: number | null;
  latency_ms_max: number | null;
  sync_quality: string;
  sync_quality_color: string;
  detail: string;
};

export type SyncReport = {
  session_id: string;
  measured_at?: string;
  devices: SyncDeviceReport[];
  overall_sync_quality: string;
  overall_sync_quality_color: string;
  server_start_time_unix_ns?: number;
  session_start_monotonic_ms?: number;
  video_start_monotonic_ms?: number;
  video_start_offset_ms?: number;
};

export type DashboardEvent = {
  type: string;
  [key: string]: unknown;
};
