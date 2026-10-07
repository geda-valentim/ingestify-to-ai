export type DatalakeProvider = "s3" | "minio" | "gcs" | "azure";
export interface PartitionField {
  field: "date" | "year" | "month" | "day" | "hour" | "project_id" | "folder_id" | "source_type" | "custom";
  key?: string | null;
}
export interface PartitionStrategy {
  mode: "none" | "date" | "project_date" | "custom";
  fields: PartitionField[];
  granularity: "month" | "day" | "hour";
  timezone: string;
  missing: "fallback" | "require";
  fallback: string;
  analytics: "none" | "jsonl";
}
export const DEFAULT_PARTITION: PartitionStrategy = { mode: "none", fields: [], granularity: "day", timezone: "UTC", missing: "fallback", fallback: "_unassigned", analytics: "none" };
export interface PartitionPreviewRequest {
  connection_id?: string;
  partitioning?: PartitionStrategy;
  partition_values?: Record<string, string>;
  prefix: string;
  created_at?: string;
  project_id?: string | null;
  folder_id?: string | null;
  source_type?: string | null;
}
export interface PartitionPreviewResponse {
  layout_id: string;
  resolved_path: string;
  partitions: Record<string, string>;
  dataset_path: string | null;
  schema_path: string | null;
  partitioning: PartitionStrategy;
}
export interface DatalakeConfig {
  endpoint: string | null;
  region: string | null;
  project_id: string | null;
  buckets: string[];
  default_bucket: string | null;
  default_prefix: string;
  partitioning?: PartitionStrategy | null;
  default_partition_values?: Record<string, string>;
}
export interface DatalakeConnection {
  id: string;
  name: string;
  provider: DatalakeProvider;
  config: DatalakeConfig;
  enabled: boolean;
  credentials_configured: boolean;
  created_at: string;
  updated_at: string;
}
export interface DatalakeDestination {
  connection_id: string;
  bucket: string;
  prefix: string;
  partitioning?: PartitionStrategy | null;
  partition_values?: Record<string, string>;
}
export interface DatalakeDelivery extends DatalakeDestination {
  connection_name: string;
  provider: DatalakeProvider;
  status: "pending" | "exporting" | "completed" | "failed";
  attempts: number;
  error: string | null;
  objects: string[];
  completed_at: string | null;
  resolved_path: string;
  layout_id: string | null;
  partitions: Record<string, string>;
  dataset_path: string | null;
  schema_path: string | null;
}
export const PROVIDER_LABELS: Record<DatalakeProvider, string> = {
  s3: "AWS S3", minio: "MinIO / S3 compatível", gcs: "Google Cloud Storage", azure: "Azure Blob Storage",
};
