import {
  AnnotationResponse,
  ArtifactResponse,
  DeviceResponse,
  HealthResponse,
  PreflightResponse,
  SessionDeviceAssignItem,
  SessionDeviceAssignmentResponse,
  SessionResponse,
  SyncReport,
  VideoAnonymizeResponse,
  VideoMetadataResponse,
  VideoStatusResponse,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
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
    body: JSON.stringify({ incomplete }),
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
