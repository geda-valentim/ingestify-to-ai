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
  /** Bind the key to a project by name (get-or-add). Exclusive with `project_id`. */
  project?: string;
  /** Bind the key to an existing project. Exclusive with `project`. */
  project_id?: string;
}

/** `PATCH /api-keys/{id}`: rebind (or, with `null`, unbind) the key's project. */
export interface APIKeyUpdate {
  project_id: string | null;
}

export interface APIKeyResponse {
  id: string;
  name: string;
  api_key: string;
  expires_at?: string | null;
  created_at: string;
  project?: ProjectRef | null;
}

export interface APIKeyInfo {
  id: string;
  name: string;
  last_used_at?: string | null;
  expires_at?: string | null;
  is_active: boolean;
  created_at: string;
  /** Where this key's uploads go when the request names no project. */
  project?: ProjectRef | null;
}

// ---------------------------------------------------------------------------
// Projects and folders (spec 0003)
// ---------------------------------------------------------------------------

/** A project as referenced from a job or an API key. */
export interface ProjectRef {
  id: string;
  name: string;
}

/** A folder as referenced from a job. */
export interface FolderRef {
  id: string;
  name: string;
}

/** A folder inside a project, as listed by `GET /projects?include=folders`. */
export interface Folder {
  id: string;
  name: string;
  job_count: number;
}

/** One project of `GET /projects`, with its counts (MAIN jobs only). */
export interface Project {
  id: string;
  name: string;
  description: string | null;
  archived: boolean;
  job_count: number;
  /** Jobs in the project that are in no folder. */
  root_job_count: number;
  failed_count: number;
  active_count: number;
  last_job_at: string | null;
  /** API keys whose uploads default to this project. */
  api_keys: { id: string; name: string }[];
  /** Present with `?include=folders`. */
  folders?: Folder[];
}

export interface ProjectsListResponse {
  /** Most recently used first, then by name. */
  projects: Project[];
  limits: {
    max_projects: number;
    max_folders_per_project: number;
  };
}

/**
 * `GET /projects/resolve?name=` and `GET /projects/{id}/folders/resolve?name=`:
 * whether a typed name matches an existing project/folder, without creating it.
 * The normalisation rule lives only in the backend; the UI asks instead of
 * re-implementing it.
 */
export interface NameResolveResponse {
  valid: boolean;
  /** The existing project/folder the name matches, or null if it would be created. */
  match?: ProjectRef | null;
  /** Why the name is not acceptable (when `valid` is false). */
  error?: string;
}

/** `project` in an upload response. */
export interface UploadProjectInfo extends ProjectRef {
  created: boolean;
  /** "api_key": the request named no project and the key's binding was used. */
  source: "request" | "api_key" | "fallback";
}

/** `folder` in an upload response. */
export interface UploadFolderInfo extends FolderRef {
  created: boolean;
}

/**
 * Where an upload goes. Exactly one of `project`/`project_id` is required by the
 * API; `folder`/`folder_id` are optional. Names are get-or-add, ids never create.
 */
export interface UploadLocation {
  project?: string;
  project_id?: string;
  folder?: string;
  folder_id?: string;
}

export interface DocumentMetadata {
  pages?: number | null;
  words?: number | null;
  format: string;
  size_bytes: number;
  title?: string | null;
  author?: string | null;
  // Audio / video transcription only
  language?: string | null;
  duration?: number | null;
  device?: string | null; // "cuda", "cpu" or "remote"
  available_formats?: TranscriptFormat[] | null;
}

/** Formats `GET /jobs/{id}/result?format=` serves for transcription jobs. */
export type TranscriptFormat = "markdown" | "vtt" | "srt" | "txt" | "json";

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
  probability: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  words?: TranscriptWord[];
}

/** Body of `?format=json` on a transcription job. */
export interface TranscriptJson {
  language: string;
  duration: number;
  text: string;
  segments: TranscriptSegment[];
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
  project?: UploadProjectInfo;
  folder?: UploadFolderInfo | null;
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
  tags?: string[];
  parent_job_id?: string | null;
  total_pages?: number | null;
  pages_completed?: number | null;
  pages_failed?: number | null;
  pages?: PageJobInfo[] | null;
  child_jobs?: ChildJobs | null;
  page_number?: number | null;
  /** Transcriptions in progress: how much of the media is done, in seconds */
  transcribed_seconds?: number | null;
  media_duration?: number | null;
  project?: ProjectRef | null;
  folder?: FolderRef | null;
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

export interface ConvertRequest extends UploadLocation {
  source_type: SourceType;
  source?: string;
  file?: File;
  name?: string;
  tags?: string[];
  authToken?: string; // OAuth token for gdrive/dropbox
}

export interface UploadRequest extends UploadLocation {
  file: File;
  name?: string;
  tags?: string[];
}

/** What a job is, from the user's point of view (derived from its source). */
export type JobKind = "document" | "transcription" | "image";

export interface JobsListParams {
  limit?: number;
  offset?: number;
  status?: JobStatus;
  job_type?: JobType | "all";
  /** Every tag must be present (AND). */
  tags?: string[];
  /** Matches the job name or file name, not the content (that is /search). */
  q?: string;
  kind?: JobKind;
  project_id?: string;
  /** A folder id, or "root" for the jobs of `project_id` that are in no folder. */
  folder_id?: string;
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface SearchParams {
  query: string;
  limit?: number;
}

/**
 * One row of `GET /jobs`.
 *
 * Deliberately not `JobStatusResponse`: the list handler builds these from the
 * MySQL row (plus live Redis progress) and returns a different set of fields
 * than the detail endpoint - no `started_at`, no `pages`, no `child_jobs`, but
 * file and tag information the detail endpoint does not carry.
 */
export interface JobListItem {
  job_id: string;
  type: JobType;
  status: JobStatus;
  progress: number;
  name?: string | null;
  filename?: string | null;
  kind: JobKind;
  source_type?: string | null;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  tags: string[];
  error?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  total_pages?: number;
  pages_completed?: number;
  page_number?: number | null;
  parent_job_id?: string | null;
  project?: ProjectRef | null;
  folder?: FolderRef | null;
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
  /** Jobs per status with every other filter applied - for the filter tabs. */
  counts: Record<JobStatus | "all", number>;
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
