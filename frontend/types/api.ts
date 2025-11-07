// Generated from OpenAPI spec

export type JobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";
export type JobType = "main" | "split" | "page" | "merge" | "download";
export type SourceType = "file" | "url" | "gdrive" | "dropbox";

export interface UserCreate {
  email: string;
  username: string;
  password: string;
}

export interface UserLogin {
  username: string;
  password: string;
}

export interface UserResponse {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface APIKeyCreate {
  name: string;
  expires_in_days?: number | null;
}

export interface APIKeyResponse {
  id: string;
  name: string;
  api_key: string;
  expires_at?: string | null;
  created_at: string;
}

export interface APIKeyInfo {
  id: string;
  name: string;
  last_used_at?: string | null;
  expires_at?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface DocumentMetadata {
  pages?: number | null;
  words?: number | null;
  format: string;
  size_bytes: number;
  title?: string | null;
  author?: string | null;
}

export interface ConversionResult {
  markdown: string;
  metadata: DocumentMetadata;
}

export interface JobCreatedResponse {
  job_id: string;
  status: "queued";
  created_at: string;
  message: string;
}

export interface ChildJobs {
  split_job_id?: string | null;
  page_job_ids?: string[] | null;
  merge_job_id?: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  type: JobType;
  status: JobStatus;
  progress: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  name?: string | null;
  parent_job_id?: string | null;
  total_pages?: number | null;
  pages_completed?: number | null;
  pages_failed?: number | null;
  pages?: PageJobInfo[] | null;
  child_jobs?: ChildJobs | null;
  page_number?: number | null;
}

export interface JobResultResponse {
  job_id: string;
  type: JobType;
  status: JobStatus;
  result: ConversionResult;
  completed_at: string;
  page_number?: number | null;
  parent_job_id?: string | null;
}

export interface PageJobInfo {
  page_number: number;
  job_id: string;
  status: JobStatus;
  url: string;
  error_message?: string | null;
  retry_count: number;
}

export interface JobPagesResponse {
  job_id: string;
  total_pages: number;
  pages_completed: number;
  pages_failed: number;
  pages: PageJobInfo[];
}

export interface HealthCheckResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  redis: boolean;
  workers: Record<string, any>;
  timestamp: string;
}

export interface ConvertRequest {
  source_type: SourceType;
  source?: string;
  file?: File;
  name?: string;
  authToken?: string; // OAuth token for gdrive/dropbox
}

export interface UploadRequest {
  file: File;
  name?: string;
}

export interface JobsListParams {
  limit?: number;
  offset?: number;
  status?: JobStatus;
  job_type?: JobType;
}

export interface SearchParams {
  query: string;
  limit?: number;
}

export interface JobsListResponse {
  jobs: JobStatusResponse[];
  total: number;
}
