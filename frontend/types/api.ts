import type { FaceAnalysisResult, ImageFullV2Result, FaceOptions } from "./faces";
// Generated from OpenAPI spec

export type JobStatus =
  | "partial"
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";
export type JobType = "main" | "split" | "page" | "merge" | "download";
export type SourceType = "file" | "url" | "gdrive" | "dropbox";

export interface UserCreate {
  email: string;
  username: string;
  password: string;
  /** Only read when this account becomes the installation's root (spec 0019). */
  setup_token?: string;
}

/** GET /auth/setup: whether the installation still needs its root user (spec 0019). */
export interface SetupStatus {
  root_exists: boolean;
  setup_token_required: boolean;
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
  /** Effective admin (users.is_admin or ADMIN_USER_IDS). Absent in sessions saved by older builds. */
  is_admin?: boolean;
  /** The installation's single root user (spec 0019). */
  is_root?: boolean;
  /** Flat list: 0009 engine permissions plus platform/IAM ones (spec 0014). */
  permissions?: string[];
  engine_access_enabled?: boolean;
  /** Emergency access (is_admin column or ADMIN_USER_IDS), never a binding. */
  bootstrap?: boolean;
  /** Managed platform roles held through active bindings (IAM_MODE=enforce only). */
  platform_roles?: string[];
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
// Projects and folders (spec 0004)
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
  schema_version?: number | null;
  speakers?: TranscriptSpeaker[] | null;
  diarization?: TranscriptJson["diarization"] | null;
  alignment?: TranscriptJson["alignment"] | null;
}

/** Formats `GET /jobs/{id}/result?format=` serves for transcription jobs. */
export type TranscriptFormat = "markdown" | "vtt" | "srt" | "txt" | "json";

export interface TranscriptWord {
  word: string;
  start: number | null;
  end: number | null;
  probability?: number | null;
  alignment_score?: number | null;
  speaker_id?: string | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  words?: TranscriptWord[];
  speaker_id?: string | null;
}

/** Body of `?format=json` on a transcription job. */
export interface TranscriptSpeaker {
  id: string;
  label: string;
}
export interface TranscriptTurn {
  start: number;
  end: number;
  speaker_id: string;
}
export interface TranscriptJson {
  schema_version?: 2;
  speakers?: TranscriptSpeaker[];
  diarization?: {
    status: "completed" | "disabled";
    speaker_count: number | null;
    turns: TranscriptTurn[];
    engine?: string;
  };
  alignment?: { status: "completed" | "unavailable"; model?: string | null };
  language: string | null;
  duration: number;
  text: string;
  segments: TranscriptSegment[];
}

export interface ConversionResult {
  markdown: string;
  metadata: DocumentMetadata;
  image?: ImageJobResult | ImageFullAnalysisResult | ImageFullV2Result | FaceAnalysisResult | null;
}

export type CaptionTask = "<CAPTION>" | "<DETAILED_CAPTION>" | "<MORE_DETAILED_CAPTION>";
export type VisionTask = CaptionTask | "<OCR>" | "<OCR_WITH_REGION>" | "<OD>" | "<DENSE_REGION_CAPTION>" | "<REGION_PROPOSAL>" | "<CAPTION_TO_PHRASE_GROUNDING>" | "<REFERRING_EXPRESSION_SEGMENTATION>" | "<REGION_TO_SEGMENTATION>" | "<OPEN_VOCABULARY_DETECTION>" | "<REGION_TO_CATEGORY>" | "<REGION_TO_DESCRIPTION>" | "<REGION_TO_OCR>";

export interface ParameterSchema {
  $ref?: string;
  readOnly?: boolean;
  "x-unavailable-reason"?: string;
  $defs?: Record<string, ParameterSchema>;
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  anyOf?: ParameterSchema[];
  properties?: Record<string, ParameterSchema>;
  items?: ParameterSchema;
}

export interface VisionTaskInfo {
  task: VisionTask;
  label: string;
  input: "none" | "text" | "region";
  output: "text" | "ocr" | "boxes" | "polygons" | "mixed";
}

export interface ImageRegion {
  label: string;
  score?: number | null;
  bbox?: number[] | null;
  quad_box?: number[] | null;
  polygons: number[][];
}

export interface ImageJobResult {
  operation: "describe" | "ocr" | "analyze";
  task: string;
  task_label?: string | null;
  image_base64?: string | null;
  image_mime_type?: string | null;
  width: number;
  height: number;
  description?: string | null;
  text?: string | null;
  lines: { text: string; quad_box: number[]; bbox: number[] }[];
  model: { model_id: string; revision: string; device: string; dtype: string };
  duration_ms: number;
  output?: Record<string, unknown> | string | null;
  regions?: ImageRegion[];
  request?: { task: VisionTask; text_input?: string | null; region?: number[] | null; generation: Record<string, unknown> } | null;
}

export interface ImageFullStepResult {
  step_id: string;
  task: VisionTask;
  input: { text_input?: string; region?: number[]; origin?: string };
  status: "pending" | "running" | "succeeded" | "failed" | "skipped" | "not_applicable";
  reason_code?: string | null;
  text?: string;
  output?: Record<string, unknown> | string;
  regions?: ImageRegion[];
  lines?: ImageJobResult["lines"];
  duration_ms?: number;
  truncated?: boolean;
}

export interface ImageFullAnalysisResult extends Omit<ImageJobResult, "operation" | "request"> {
  operation: "full_analysis";
  schema_version: string;
  profile: string;
  analysis_status: "completed" | "partial" | "failed" | "cancelled";
  reason_code?: string | null;
  coverage: { task_families_total: number; task_families_completed: number; instances_planned: number; instances_completed: number;
    families: { task: VisionTask; label: string; completed: boolean; instances: number; succeeded: number }[] };
  resolved_inputs: { queries?: unknown[]; regions?: unknown[]; omitted_candidates?: unknown[] };
  results: ImageFullStepResult[];
  calls_started: number;
  request?: Record<string, unknown> | null;
}

export interface VisionCapabilities {
  full_profiles?: { profile: "image-full-v1" | "image-full-v2"; ready: boolean; families: number; max_calls: number; max_faces: number }[];
  analysis_modes?: string[];
  full_limits?: { max_queries: number; max_regions: number; max_calls: number; deadline_seconds: number };
  enabled: boolean;
  dependencies_installed: boolean;
  model_downloaded: boolean;
  reason?: string | null;
  max_image_size_mb: number;
  caption_tasks: CaptionTask[];
  default_caption_task: CaptionTask;
  tasks: VisionTaskInfo[];
  generation_schema: ParameterSchema;
  generation_defaults: Record<string, unknown>;
}

export interface JobCreatedResponse {
  job_id: string;
  status: "queued" | "completed";
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
  kind?: JobKind | null;
  configuration?: { operation: string; provider?: string | null; model?: string | null; options: Record<string, unknown> } | null;
  image_analysis?: { status: string; steps_total: number; steps_completed: number; calls_started: number; cancel_requested: boolean };
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
  phase?: "transcribing" | "aligning" | "diarizing" | "saving" | null;
  media_duration?: number | null;
  project?: ProjectRef | null;
  folder?: FolderRef | null;
  /** Only with routing (spec 0003): where the job runs. Never the engine's name or cost. */
  engine?: { kind: "local" | "cloud" } | null;
  /** Only with routing: why it still waits (`in_queue` = backlog, `starting` = placed, not started). */
  queue_reason?: "in_queue" | "starting" | null;
}

/** The text of a running transcription, from segment `since` on */
export interface PartialTranscriptResponse {
  job_id: string;
  status: JobStatus;
  segments: TranscriptSegment[];
  /** Pass as `since` next time to get only what is new */
  next: number;
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
  datalake?: import("./datalake").DatalakeDestination;
  image_operation?: "describe" | "ocr" | "analyze" | "full" | "faces";
  face_options?: FaceOptions;
  image_engine?: "vision" | "docling";
  image_task?: VisionTask;
  image_text_input?: string;
  image_region?: number[];
  image_generation?: Record<string, unknown>;
  image_full_options?: { profile?: "image-full-v1" | "image-full-v2"; faces?: FaceOptions; queries?: string[]; regions?: number[][]; deadline_seconds?: number };
  image_idempotency_key?: string;

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
