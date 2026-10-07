import { API_URL, apiFetch, getHeaders, throwApiError } from "@/lib/api";
import type { DatalakeConfig, DatalakeConnection, DatalakeDelivery, DatalakeDestination, DatalakeProvider, PartitionPreviewRequest, PartitionPreviewResponse } from "@/types/datalake";
import type { JobCreatedResponse, UploadLocation } from "@/types/api";

export interface ConnectionWrite {
  name: string;
  config: DatalakeConfig;
  credentials?: Record<string, string>;
  enabled?: boolean;
}

async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await apiFetch(API_URL + path, {
    method, headers: { ...getHeaders(true), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) await throwApiError(response, "Não foi possível acessar o datalake");
  return response.status === 204 ? undefined as T : response.json();
}

export const datalakeApi = {
  partitionPreview: (body: PartitionPreviewRequest) => call<PartitionPreviewResponse>("/datalakes/partition-preview", "POST", body),
  list: () => call<{ connections: DatalakeConnection[] }>("/datalakes"),
  discover: (body: { provider: DatalakeProvider; config: DatalakeConfig; credentials?: Record<string, string>; connection_id?: string; bucket?: string }) => call<{ buckets: string[]; verified: boolean }>("/datalakes/discover", "POST", body),
  createBucket: (body: { provider: DatalakeProvider; config: DatalakeConfig; credentials?: Record<string, string>; connection_id?: string; bucket: string; location?: string }) => call<{ bucket: string; created: boolean; location: string | null }>("/datalakes/buckets", "POST", body),
  create: (body: ConnectionWrite & { provider: DatalakeProvider; credentials: Record<string, string> }) => call<DatalakeConnection>("/datalakes", "POST", body),
  update: (id: string, body: Partial<ConnectionWrite>) => call<DatalakeConnection>(`/datalakes/${id}`, "PATCH", body),
  remove: (id: string) => call<void>(`/datalakes/${id}`, "DELETE"),
  test: (id: string, bucket?: string) => call<{ ok: boolean }>(`/datalakes/${id}/test`, "POST", { bucket: bucket || null }),
  buckets: (id: string) => call<{ buckets: string[] }>(`/datalakes/${id}/buckets`),
  objects: (id: string, bucket: string, prefix: string) => call<{ objects: { key: string; size: number }[] }>(`/datalakes/${id}/objects?${new URLSearchParams({ bucket, prefix })}`),
  import: (body: UploadLocation & { docling_preset?: string; conversion_options?: import("@/types/api").DocumentOptions; audio_options?: import("@/types/api").AudioConversionOptions; connection_id: string; bucket: string; key: string; name?: string; tags?: string[]; datalake?: DatalakeDestination }) => call<JobCreatedResponse>("/datalakes/import", "POST", body),
  delivery: (id: string) => call<{ destination: DatalakeDelivery | null }>(`/jobs/${id}/datalake`),
  retry: (id: string) => call<{ destination: DatalakeDelivery }>(`/jobs/${id}/datalake/retry`, "POST"),
};
