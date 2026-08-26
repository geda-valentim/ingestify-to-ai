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
  /**
   * `null` until the split task has created this page's job.
   *
   * The API publishes `total_pages` before the page rows exist, so a page can
   * be listed with no job behind it yet. It used to fabricate an id
   * ("pending-3") for that case; nothing addressable lives at it. Anything that
   * fetches by page job id must handle the null.
   */
  job_id: string | null;
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

/**
 * Short-lived, presigned URL for a page PDF.
 *
 * The URL points straight at object storage and is signed for a few minutes -
 * it must be fetched as-is: appending anything (a cache-busting `?t=`, for
 * example) invalidates the signature. Refetch once `expires_at` has passed.
 */
export interface PagePdfUrlResponse {
  job_id: string;
  page_number: number;
  url: string;
  expires_in: number;
  expires_at: string;
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

/**
 * One row of `GET /jobs`.
 *
 * Deliberately not `JobStatusResponse`: the list handler builds these by hand
 * from Redis + MySQL and returns strictly less than the detail endpoint - no
 * `started_at`, no `pages`, no `child_jobs` - and `created_at`/`completed_at`
 * are null whenever the MySQL row is missing. Reusing `JobStatusResponse` here
 * would be the same kind of false claim that hid this bug in the first place.
 */
export interface JobListItem {
  job_id: string;
  type: JobType;
  status: JobStatus;
  progress: number;
  name?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  total_pages?: number;
  pages_completed?: number;
  page_number?: number | null;
  parent_job_id?: string | null;
}

/**
 * `GET /jobs` answers an envelope, never a bare array.
 *
 * `total` is the count *after* filtering and *before* pagination, so it - not
 * `jobs.length` - drives the pager. Treating the envelope as an array is what
 * made "My Jobs" render empty for every user regardless of job count.
 */
export interface JobsListResponse {
  total: number;
  limit: number;
  offset: number;
  jobs: JobListItem[];
}

/**
 * One hit from `GET /search`.
 *
 * A search hit is not a job: it is a match inside an indexed document. It
 * carries the evidence for the match (`preview`) and no live job state - the
 * Elasticsearch index only holds finished conversions, and re-deriving
 * status/progress per hit would mean a Redis round trip each and would lose
 * every document whose Redis key has since expired.
 */
export interface SearchResult {
  job_id: string;
  filename?: string | null;
  total_pages?: number | null;
  char_count?: number | null;
  created_at?: string | null;
  preview: string;
}

export interface SearchResponse {
  query: string;
  total: number;
  limit: number;
  results: SearchResult[];
}
