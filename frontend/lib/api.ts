import { useAuthStore } from "@/lib/store/auth";
import { expireSession } from "@/lib/session";
import type {
  UserCreate,
  SetupStatus,
  UserLogin,
  UserResponse,
  Token,
  APIKeyCreate,
  APIKeyResponse,
  APIKeyInfo,
  APIKeyUpdate,
  ProjectsListResponse,
  NameResolveResponse,
  UploadLocation,
  JobCreatedResponse,
  JobStatusResponse,
  JobResultResponse,
  JobPagesResponse,
  PartialTranscriptResponse,
  PagePdfUrlResponse,
  TagCount,
  TranscriptFormat,
  ConvertRequest,
  UploadRequest,
  JobsListParams,
  JobsListResponse,
  SearchParams,
  SearchResponse,
} from "@/types/api";
import type { AdapterDescriptor, Engine, EnginesStatus, FeatureRoute, GpusResponse } from "@/types/compute";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  // The store is the source of truth; `auth_token` is where older builds kept it.
  return useAuthStore.getState().token ?? localStorage.getItem("auth_token");
}

/**
 * fetch, plus: a 401 on a request that carried our session token means the
 * session is over (expired or revoked), so it is ended everywhere at once
 * instead of leaving each page to spin or show a raw error.
 */
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401 && new Headers(init?.headers).has("Authorization")) {
    expireSession();
  }
  return response;
}

/**
 * An HTTP error that keeps the server's body, so `formatApiError` can show
 * FastAPI's `detail` (e.g. the 422 "project required" message with its curl
 * example) instead of a bare status text.
 */
export class ApiError extends Error {
  status: number;
  response: { status: number; data: unknown };

  constructor(status: number, data: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.response = { status, data };
  }
}

export async function throwApiError(response: Response, fallback: string): Promise<never> {
  const data = await response.json().catch(() => null);
  const detail = (data as { detail?: unknown } | null)?.detail;
  const message = typeof detail === "string" && detail ? detail : `${fallback}: ${response.statusText}`;
  throw new ApiError(response.status, data, message);
}

/** Add the project/folder fields of an upload, skipping the empty ones. */
function appendLocation(formData: FormData, location: UploadLocation) {
  if (location.project_id) formData.append("project_id", location.project_id);
  else if (location.project?.trim()) formData.append("project", location.project.trim());
  if (location.folder_id) formData.append("folder_id", location.folder_id);
  else if (location.folder?.trim()) formData.append("folder", location.folder.trim());
}

export function getHeaders(includeAuth = false): HeadersInit {
  const headers: HeadersInit = {};

  if (includeAuth) {
    const token = getAuthToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  return headers;
}

// Auth API
export const authApi = {
  async setupStatus(): Promise<SetupStatus> {
    const response = await apiFetch(`${API_URL}/auth/setup`);
    if (!response.ok) {
      throw new Error("Could not read the installation setup state");
    }
    return response.json();
  },

  async register(data: UserCreate): Promise<{ message: string }> {
    const response = await apiFetch(`${API_URL}/auth/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Registration failed" }));
      throw { response: { data: error } };
    }

    return response.json();
  },

  async login(data: UserLogin): Promise<Token> {
    const formData = new URLSearchParams();
    formData.append("username", data.username);
    formData.append("password", data.password);

    const response = await apiFetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Login failed" }));
      throw { response: { data: error } };
    }

    return response.json();
  },

  /** Trade the current, still valid JWT for a fresh one (the session heartbeat). */
  async refresh(): Promise<Token> {
    const response = await apiFetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Session refresh failed: ${response.statusText}`);
    }

    return response.json();
  },

  async me(): Promise<UserResponse> {
    const response = await apiFetch(`${API_URL}/auth/me`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error("Failed to fetch user profile");
    }

    return response.json();
  },
};

// Jobs API
export function uploadSourceType(filename: string): "audio" | "file" | "image" {
  if (/\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(filename)) return "image";
  return /\.(mp3|mp4|m4v|wav|flac|ogg|oga|spx|m4a|aac|wma|webm|mkv|avi|mov|opus|wmv|flv|mpeg|mpg|ts|3gp)$/i.test(filename) ? "audio" : "file";
}

export const jobsApi = {
  async faceCapabilities(): Promise<import("@/types/faces").FaceCapabilities> {
    const response = await apiFetch(`${API_URL}/images/faces/capabilities`, { headers: getHeaders(true) });
    if (!response.ok) await throwApiError(response, "Facial capabilities unavailable");
    return response.json();
  },

  async imageCapabilities(): Promise<import("@/types/api").VisionCapabilities> {
    const response = await apiFetch(`${API_URL}/images/capabilities`, { headers: getHeaders(true) });
    if (!response.ok) await throwApiError(response, "Could not load image capabilities");
    return response.json();
  },

  async cancelFullImage(jobId: string): Promise<void> {
    const response = await apiFetch(`${API_URL}/images/${jobId}/cancel`, { method: "POST", headers: getHeaders(true) });
    if (!response.ok) await throwApiError(response, "Não foi possível cancelar a análise");
  },

  async convert(request: ConvertRequest): Promise<JobCreatedResponse> {
    const formData = new FormData();
    formData.append("source_type", request.source_type);

    if (request.file) {
      formData.append("file", request.file);
    }

    if (request.source) {
      formData.append("source", request.source);
    }

    if (request.name) {
      formData.append("name", request.name);
    }

    if (request.tags?.length) {
      formData.append("tags", request.tags.join(","));
    }

    if (request.authToken) {
      formData.append("auth_token", request.authToken);
    }

    appendLocation(formData, request);

    const response = await apiFetch(`${API_URL}/convert`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData,
    });

    if (!response.ok) {
      await throwApiError(response, "Conversion failed");
    }

    return response.json();
  },

  async upload(request: UploadRequest): Promise<JobCreatedResponse> {
    if (uploadSourceType(request.file.name) === "image") {
      const body = new FormData();
      body.append("file", request.file);
      if (request.tags?.length) body.append("tags", request.tags.join(","));
      appendLocation(body, request);
      const operation = request.image_operation ?? "describe";
      const full = operation === "full";
      const faces = operation === "faces";
      const analyze = !faces && (full || operation === "analyze" || !!Object.keys(request.image_generation ?? {}).length);
      if (faces) {
        body.append("face_options", JSON.stringify(request.face_options ?? {}));
        body.append("wait", "false");
        if (request.datalake) body.append("datalake", JSON.stringify(request.datalake));
      } else if (full) {
        body.append("mode", "full");
        body.append("wait", "false");
        body.append("full_options", JSON.stringify({ ...request.image_full_options, generation: request.image_generation ?? {} }));
        if (request.datalake) body.append("datalake", JSON.stringify(request.datalake));
      } else if (analyze) {
        body.append("task", request.image_task ?? (operation === "ocr" ? "<OCR_WITH_REGION>" : "<MORE_DETAILED_CAPTION>"));
        body.append("wait", "false");
        if (request.image_text_input) body.append("text_input", request.image_text_input);
        if (request.image_region) body.append("region", JSON.stringify(request.image_region));
        if (request.image_generation && Object.keys(request.image_generation).length) body.append("generation", JSON.stringify(request.image_generation));
      } else if (operation === "describe" && request.image_task) body.append("task", request.image_task);
      const response = await apiFetch(faces ? `${API_URL}/images/faces/upload` : analyze ? `${API_URL}/images/analyze/upload` : operation === "ocr" ? `${API_URL}/images/ocr/upload` : `${API_URL}/images/describe/upload`, {
        method: "POST", headers: { ...getHeaders(true), ...((full || faces) ? { "Idempotency-Key": request.image_idempotency_key ?? crypto.randomUUID() } : {}) }, body,
      });
      const data = await response.json().catch(() => null);
      // The synchronous endpoint can time out while its owned job continues.
      // Follow that job instead of asking the user to upload it a second time.
      if (response.status === 504 && data?.detail?.job_id) {
        return { job_id: data.detail.job_id, status: "queued", created_at: new Date().toISOString(), message: "Image processing continues" };
      }
      if (!response.ok) throw new ApiError(response.status, data, data?.detail?.message ?? "Image upload failed");
      return { ...data, created_at: new Date().toISOString(), message: "Image processed" };
    }

    const formData = new FormData();
    formData.append("file", request.file);

    if (request.name) {
      formData.append("name", request.name);
    }

    if (request.tags?.length) {
      formData.append("tags", request.tags.join(","));
    }

    appendLocation(formData, request);

    const response = await apiFetch(`${API_URL}/upload`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData,
    });

    if (!response.ok) {
      await throwApiError(response, "Upload failed");
    }

    return response.json();
  },

  async getStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job status: ${response.statusText}`);
    }

    return response.json();
  },

  async getResult(jobId: string): Promise<JobResultResponse> {
    // Explicit format: a transcription job created with output_format=vtt (or
    // srt/txt/json) answers a bare /result with that file, not with this JSON.
    const response = await apiFetch(`${API_URL}/jobs/${jobId}/result?format=markdown`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job result: ${response.statusText}`);
    }

    return response.json();
  },

  /** The text of a transcription while it runs, from segment `since` on. */
  async getPartialTranscript(jobId: string, since: number): Promise<PartialTranscriptResponse> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}/transcript/partial?since=${since}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch live transcript: ${response.statusText}`);
    }

    return response.json();
  },

  /** One transcript format of a transcription job, as raw text (VTT, SRT, TXT or JSON). */
  async getTranscriptFile(jobId: string, format: Exclude<TranscriptFormat, "markdown">): Promise<string> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}/result?format=${format}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch ${format} transcript: ${response.statusText}`);
    }

    return response.text();
  },

  async getPages(jobId: string): Promise<JobPagesResponse> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}/pages`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job pages: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * List the caller's jobs.
   *
   * Returns the server's envelope verbatim. This used to declare
   * `Promise<JobStatusResponse[]>` while handing back `{total, limit, offset,
   * jobs}`; `response.json()` is `any`, so the declaration was simply false and
   * `tsc` had nothing to object to. Every consumer then treated the object as
   * an array and rendered nothing.
   */
  async list(params?: JobsListParams): Promise<JobsListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());
    if (params?.status) searchParams.set("status", params.status);
    if (params?.job_type) searchParams.set("job_type", params.job_type);
    if (params?.q) searchParams.set("q", params.q);
    if (params?.kind) searchParams.set("kind", params.kind);
    params?.tags?.forEach((tag) => searchParams.append("tag", tag));
    if (params?.project_id) searchParams.set("project_id", params.project_id);
    if (params?.folder_id) searchParams.set("folder_id", params.folder_id);

    const url = `${API_URL}/jobs${searchParams.toString() ? `?${searchParams}` : ""}`;
    const response = await apiFetch(url, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      await throwApiError(response, "Failed to fetch jobs");
    }

    return response.json();
  },

  /**
   * Full-text search over converted document content.
   *
   * The route is `/search`, not `/jobs/search`. `/jobs/search` is not a route at
   * all - it matches `GET /jobs/{job_id}` with `job_id="search"`, so every
   * keystroke used to come back as a confident, wrong 404 "Job não encontrado".
   */
  async search(params: SearchParams): Promise<SearchResponse> {
    const searchParams = new URLSearchParams();
    searchParams.set("query", params.query);
    if (params.limit) searchParams.set("limit", params.limit.toString());

    const response = await apiFetch(`${API_URL}/search?${searchParams}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    return response.json();
  },

  // `cancel()` used to live here, calling POST /jobs/{job_id}/cancel. That
  // route does not exist and never has - the API has no cancel operation - so
  // the method could only ever have thrown. It had no call sites; removed
  // rather than left as a trap for whoever wires up a Cancel button next.
  // Reinstating it means adding the endpoint first.

  async getPageResultByNumber(jobId: string, pageNumber: number): Promise<JobResultResponse> {
    // First get all pages to find the job_id for this page number
    const pagesResponse = await this.getPages(jobId);
    const page = pagesResponse.pages.find((p) => p.page_number === pageNumber);

    if (!page) {
      throw new Error(`Page ${pageNumber} not found`);
    }

    // A listed page can have no job yet (see PageJobInfo.job_id).
    if (!page.job_id) {
      throw new Error(`Page ${pageNumber} has not been queued for conversion yet`);
    }

    // Then get the result for that specific page job
    return this.getResult(page.job_id);
  },

  async delete(jobId: string): Promise<{ message: string }> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}`, {
      method: "DELETE",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to delete job: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Re-queue a page that failed, and return the id of the new page job.
   *
   * Addressed by (main job id, page number) - not by the failed page's own job
   * id. `POST /jobs/{pageJobId}/retry` is not a route, so every retry 404'd;
   * the live route is `POST /jobs/{job_id}/pages/{page_number}/retry`, and it
   * has to be, because a retry mints a *new* page job and the server needs to
   * know which page of which document it belongs to. The server answers with
   * `new_page_job_id`; the old client read `new_job_id`, which never exists.
   */
  async retryPage(jobId: string, pageNumber: number): Promise<string> {
    const response = await apiFetch(
      `${API_URL}/jobs/${jobId}/pages/${pageNumber}/retry`,
      {
        method: "POST",
        headers: getHeaders(true),
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to retry page: ${response.statusText}`);
    }

    const data = await response.json();
    return data.new_page_job_id;
  },

  /**
   * Ask the API for a short-lived presigned URL for a page's PDF.
   *
   * The endpoint is authenticated (it used to be public, which leaked every
   * user's PDFs to anyone holding a job id) and answers JSON rather than a
   * redirect - a redirect could not carry this Authorization header to the
   * object storage, and the caller needs to know when the URL expires.
   *
   * The returned `url` must be handed to the PDF viewer untouched: the query
   * string is part of the signature.
   */
  async getPagePdf(jobId: string, pageNumber: number): Promise<PagePdfUrlResponse> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}/pages/${pageNumber}/pdf`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to get page PDF URL: ${response.statusText}`);
    }

    return response.json();
  },
};

// Tags API
export const tagsApi = {
  /** Every tag on the user's jobs, most used first. */
  async list(): Promise<TagCount[]> {
    const response = await apiFetch(`${API_URL}/tags`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch tags: ${response.statusText}`);
    }

    return (await response.json()).tags;
  },

  /** Replace a job's tags (normalised by the server; the result is what was stored). */
  async setForJob(jobId: string, tags: string[]): Promise<string[]> {
    const response = await apiFetch(`${API_URL}/jobs/${jobId}/tags`, {
      method: "PUT",
      headers: { ...getHeaders(true), "Content-Type": "application/json" },
      body: JSON.stringify({ tags }),
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail || `Failed to save tags: ${response.statusText}`);
    }

    return (await response.json()).tags;
  },
};

// Projects API (spec 0004, phase 1: read-only; projects and folders are
// created by get-or-add on upload)
export const projectsApi = {
  /** The user's projects with job counts, most recently used first. */
  async list(includeFolders = true): Promise<ProjectsListResponse> {
    const query = includeFolders ? "?include=folders" : "";
    const response = await apiFetch(`${API_URL}/projects${query}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      await throwApiError(response, "Failed to fetch projects");
    }

    return response.json();
  },

  /** Whether `name` matches an existing project (by the backend's rule), without creating one. */
  async resolve(name: string): Promise<NameResolveResponse> {
    const response = await apiFetch(
      `${API_URL}/projects/resolve?name=${encodeURIComponent(name)}`,
      { headers: getHeaders(true) }
    );

    if (!response.ok) {
      await throwApiError(response, "Failed to check the project name");
    }

    return response.json();
  },

  /** Same as `resolve`, for a folder inside `projectId`. */
  async resolveFolder(projectId: string, name: string): Promise<NameResolveResponse> {
    const response = await apiFetch(
      `${API_URL}/projects/${encodeURIComponent(projectId)}/folders/resolve?name=${encodeURIComponent(name)}`,
      { headers: getHeaders(true) }
    );

    if (!response.ok) {
      await throwApiError(response, "Failed to check the folder name");
    }

    return response.json();
  },
};

// API Keys API
export const apiKeysApi = {
  async list(): Promise<APIKeyInfo[]> {
    const response = await apiFetch(`${API_URL}/api-keys`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to list API keys: ${response.statusText}`);
    }

    // A bare array (`response_model=List[APIKeyInfo]`). There is no `api_keys`
    // envelope; unwrapping one produced an empty list for every user, forever.
    return response.json();
  },

  async create(request: APIKeyCreate): Promise<APIKeyResponse> {
    const response = await apiFetch(`${API_URL}/api-keys`, {
      method: "POST",
      headers: {
        ...getHeaders(true),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      await throwApiError(response, "Failed to create API key");
    }

    return response.json();
  },

  /** Rebind the key to another project, or unbind it with `null`. */
  async setProject(keyId: string, projectId: string | null): Promise<void> {
    const body: APIKeyUpdate = { project_id: projectId };
    const response = await apiFetch(`${API_URL}/api-keys/${keyId}`, {
      method: "PATCH",
      headers: {
        ...getHeaders(true),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      await throwApiError(response, "Failed to update API key");
    }
    // The body is not relied on (the spec does not pin it down); callers refetch the list.
  },

  /**
   * Revoke an API key.
   *
   * The server answers 204 No Content, so there is no body to parse. Calling
   * `response.json()` on it threw *after* the key had already been destroyed:
   * the revoke succeeded and the UI reported failure.
   */
  async revoke(keyId: string): Promise<void> {
    const response = await apiFetch(`${API_URL}/api-keys/${keyId}`, {
      method: "DELETE",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to revoke API key: ${response.statusText}`);
    }
  },
};

async function adminGet<T>(path: string): Promise<T> {
  const response = await apiFetch(`${API_URL}${path}`, { headers: getHeaders(true) });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    // ApiError keeps the HTTP status: the admin pages tell 403 and 404 apart
    throw new ApiError(response.status, body, detail || `Request failed (${response.status})`);
  }
  return response.json();
}

/**
 * Execution engines, capacity and routing (spec 0003). Read-only on purpose: the
 * v1 admin UI shows state and the CLI command that changes it (spec 0003, 4.6.8),
 * so the mutation endpoints under /admin/engines and /admin/routing are not here.
 */
export const computeApi = {
  adapters: () => adminGet<AdapterDescriptor[]>("/admin/engine-adapters"),
  engines: () => adminGet<Engine[]>("/admin/engines"),
  engine: (idOrSlug: string) => adminGet<Engine>(`/admin/engines/${encodeURIComponent(idOrSlug)}`),
  gpus: () => adminGet<GpusResponse>("/admin/gpus"),
  routing: () => adminGet<FeatureRoute[]>("/admin/routing"),
  status: () => adminGet<EnginesStatus>("/admin/engines/status"),
};

export const liveApi = {
  async getStatus(jobId: string): Promise<{ job_id: string; state: string; duration_seconds: number; error_code: string | null }> {
    const response = await apiFetch(`${API_URL}/transcribe/live/sessions/${jobId}`, { headers: getHeaders(true) });
    if (!response.ok) await throwApiError(response, "Não foi possível consultar a sessão");
    return response.json();
  },
  async create(body: UploadLocation & { name: string; language: "pt"; protocol?: 1 | 2; diarize?: boolean }): Promise<{
    job_id: string; ws_url: string; ticket: string; max_duration_seconds: number; protocol?: 1 | 2;
  }> {
    const response = await apiFetch(`${API_URL}/transcribe/live/sessions`, {
      method: "POST", headers: { ...getHeaders(true), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) await throwApiError(response, "Serviço de transcrição ao vivo indisponível");
    return response.json();
  },
  async cancel(jobId: string): Promise<void> {
    const response = await apiFetch(`${API_URL}/transcribe/live/sessions/${jobId}`, {
      method: "DELETE", headers: getHeaders(true),
    });
    if (!response.ok) await throwApiError(response, "Não foi possível cancelar a sessão");
  },
};
