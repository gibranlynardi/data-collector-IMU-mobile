import {
  AnnotationResponse,
  ArchiveUploadStatusResponse,
  ArtifactResponse,
  DeviceResponse,
  HealthResponse,
  PreflightResponse,
  SessionCompletenessResponse,
  SessionSamplingQualityHistoryResponse,
  SessionDeviceAssignItem,
  SessionDeviceAssignmentResponse,
  SessionResponse,
  SyncReport,
  UploadInstructionsResponse,
  VideoAnonymizeResponse,
  VideoMetadataResponse,
  VideoStatusResponse,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const OPERATOR_TOKEN = process.env.NEXT_PUBLIC_OPERATOR_API_TOKEN ?? "";
const OPERATOR_ID = process.env.NEXT_PUBLIC_OPERATOR_ID ?? "dashboard-web";

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(OPERATOR_TOKEN ? { "X-Operator-Token": OPERATOR_TOKEN } : {}),
      ...(OPERATOR_ID ? { "X-Operator-Id": OPERATOR_ID } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    ...init,
  });

  const rawBody = await response.text();
  let parsedBody: unknown = null;
  if (rawBody) {
    try {
      parsedBody = JSON.parse(rawBody);
    } catch {
      parsedBody = rawBody;
    }
  }

  if (!response.ok) {
    let detailMessage = `Request failed (${response.status})`;
    if (typeof parsedBody === "string" && parsedBody.trim()) {
      detailMessage = parsedBody;
    } else if (
      parsedBody &&
      typeof parsedBody === "object" &&
      "detail" in parsedBody &&
      typeof (parsedBody as { detail?: unknown }).detail === "string"
    ) {
      detailMessage = String((parsedBody as { detail: string }).detail);
    }
    throw new ApiError(detailMessage, response.status, parsedBody);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (parsedBody as T) ?? (undefined as T);
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function fetchPreflight(): Promise<PreflightResponse> {
  return request<PreflightResponse>("/preflight");
}

export async function fetchDevices(): Promise<DeviceResponse[]> {
  return request<DeviceResponse[]>("/devices");
}

export async function createSession(payload: { session_id?: string; override_reason?: string | null }): Promise<SessionResponse> {
  return request<SessionResponse>("/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchSession(sessionId: string): Promise<SessionResponse> {
  return request<SessionResponse>(`/sessions/${sessionId}`);
}

export async function startSession(sessionId: string): Promise<SessionResponse> {
  return request<SessionResponse>(`/sessions/${sessionId}/start`, { method: "POST" });
}

export async function stopSession(sessionId: string): Promise<SessionResponse> {
  return request<SessionResponse>(`/sessions/${sessionId}/stop`, { method: "POST" });
}

export async function finalizeSession(sessionId: string, incomplete = false): Promise<SessionResponse> {
  return request<SessionResponse>(`/sessions/${sessionId}/finalize`, {
    method: "POST",
    body: JSON.stringify({ incomplete, reason: null }),
  });
}

export async function finalizeSessionWithReason(sessionId: string, reason: string): Promise<SessionResponse> {
  return request<SessionResponse>(`/sessions/${sessionId}/finalize`, {
    method: "POST",
    body: JSON.stringify({ incomplete: true, reason }),
  });
}

export async function fetchSessionDevices(sessionId: string): Promise<SessionDeviceAssignmentResponse> {
  return request<SessionDeviceAssignmentResponse>(`/sessions/${sessionId}/devices`);
}

export async function assignSessionDevices(
  sessionId: string,
  assignments: SessionDeviceAssignItem[],
  replace = true,
): Promise<SessionDeviceAssignmentResponse> {
  return request<SessionDeviceAssignmentResponse>(`/sessions/${sessionId}/devices`, {
    method: "PUT",
    body: JSON.stringify({ assignments, replace }),
  });
}

export async function fetchAnnotations(sessionId: string): Promise<AnnotationResponse[]> {
  return request<AnnotationResponse[]>(`/sessions/${sessionId}/annotations`);
}

export async function startAnnotation(sessionId: string, payload: { label: string; notes?: string }): Promise<AnnotationResponse> {
  return request<AnnotationResponse>(`/sessions/${sessionId}/annotations/start`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function stopAnnotation(sessionId: string, annotationId: string): Promise<AnnotationResponse> {
  return request<AnnotationResponse>(`/sessions/${sessionId}/annotations/${annotationId}/stop`, {
    method: "POST",
  });
}

export async function patchAnnotation(
  annotationId: string,
  payload: Partial<{ label: string; notes: string; started_at: string; ended_at: string | null }>,
): Promise<AnnotationResponse> {
  return request<AnnotationResponse>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAnnotation(annotationId: string): Promise<{ deleted: boolean; annotation_id: string }> {
  return request<{ deleted: boolean; annotation_id: string }>(`/annotations/${annotationId}`, {
    method: "DELETE",
  });
}

export async function fetchArtifacts(sessionId: string): Promise<ArtifactResponse[]> {
  return request<ArtifactResponse[]>(`/sessions/${sessionId}/artifacts`);
}

export async function fetchUploadInstructions(sessionId: string): Promise<UploadInstructionsResponse> {
  return request<UploadInstructionsResponse>(`/sessions/${sessionId}/upload-instructions`);
}

export async function fetchArchiveUploadStatus(sessionId: string): Promise<ArchiveUploadStatusResponse> {
  return request<ArchiveUploadStatusResponse>(`/sessions/${sessionId}/archive-upload`);
}

export async function markArchiveUploaded(
  sessionId: string,
  payload: { uploaded_by: string; remote_path: string; checksum: string },
): Promise<ArchiveUploadStatusResponse> {
  return request<ArchiveUploadStatusResponse>(`/sessions/${sessionId}/archive-upload/mark-uploaded`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchSessionCompleteness(sessionId: string): Promise<SessionCompletenessResponse> {
  return request<SessionCompletenessResponse>(`/sessions/${sessionId}/completeness`);
}

export async function fetchSessionSamplingQualityHistory(
  sessionId: string,
  options?: { deviceId?: string; limit?: number },
): Promise<SessionSamplingQualityHistoryResponse> {
  const params = new URLSearchParams();
  if (options?.deviceId) {
    params.set("device_id", options.deviceId);
  }
  if (typeof options?.limit === "number") {
    params.set("limit", String(options.limit));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<SessionSamplingQualityHistoryResponse>(`/sessions/${sessionId}/sampling-quality${suffix}`);
}

export function webcamSnapshotUrl(): string {
  return `${API_BASE_URL}/health/webcam-snapshot.jpg`;
}

export async function fetchSyncReport(sessionId: string): Promise<SyncReport> {
  return request<SyncReport>(`/sessions/${sessionId}/sync-report`);
}

export async function fetchVideoStatus(sessionId: string): Promise<VideoStatusResponse> {
  return request<VideoStatusResponse>(`/sessions/${sessionId}/video/status`);
}

export async function fetchVideoMetadata(sessionId: string): Promise<VideoMetadataResponse> {
  return request<VideoMetadataResponse>(`/sessions/${sessionId}/video/metadata`);
}

export async function anonymizeVideo(sessionId: string): Promise<VideoAnonymizeResponse> {
  return request<VideoAnonymizeResponse>(`/sessions/${sessionId}/video/anonymize`, { method: "POST" });
}
