import type {
  UserCreate,
  UserLogin,
  UserResponse,
  Token,
  APIKeyCreate,
  APIKeyResponse,
  APIKeyInfo,
  JobCreatedResponse,
  JobStatusResponse,
  JobResultResponse,
  JobPagesResponse,
  ConvertRequest,
  UploadRequest,
  JobsListParams,
  SearchParams,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

function getHeaders(includeAuth = false): HeadersInit {
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
  async register(data: UserCreate): Promise<{ message: string }> {
    const response = await fetch(`${API_URL}/auth/register`, {
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

    const response = await fetch(`${API_URL}/auth/login`, {
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

  async me(): Promise<UserResponse> {
    const response = await fetch(`${API_URL}/auth/me`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error("Failed to fetch user profile");
    }

    return response.json();
  },
};

// Jobs API
export const jobsApi = {
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

    if (request.authToken) {
      formData.append("auth_token", request.authToken);
    }

    const response = await fetch(`${API_URL}/convert`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Conversion failed: ${response.statusText}`);
    }

    return response.json();
  },

  async upload(request: UploadRequest): Promise<JobCreatedResponse> {
    const formData = new FormData();
    formData.append("file", request.file);

    if (request.name) {
      formData.append("name", request.name);
    }

    const response = await fetch(`${API_URL}/upload`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
  },

  async getStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await fetch(`${API_URL}/jobs/${jobId}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job status: ${response.statusText}`);
    }

    return response.json();
  },

  async getResult(jobId: string): Promise<JobResultResponse> {
    const response = await fetch(`${API_URL}/jobs/${jobId}/result`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job result: ${response.statusText}`);
    }

    return response.json();
  },

  async getPages(jobId: string): Promise<JobPagesResponse> {
    const response = await fetch(`${API_URL}/jobs/${jobId}/pages`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job pages: ${response.statusText}`);
    }

    return response.json();
  },

  async list(params?: JobsListParams): Promise<JobStatusResponse[]> {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());
    if (params?.status) searchParams.set("status", params.status);
    if (params?.job_type) searchParams.set("job_type", params.job_type);

    const url = `${API_URL}/jobs${searchParams.toString() ? `?${searchParams}` : ""}`;
    const response = await fetch(url, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch jobs: ${response.statusText}`);
    }

    return response.json();
  },

  async search(params: SearchParams): Promise<JobStatusResponse[]> {
    const searchParams = new URLSearchParams();
    searchParams.set("query", params.query);
    if (params.limit) searchParams.set("limit", params.limit.toString());

    const response = await fetch(`${API_URL}/jobs/search?${searchParams}`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    return response.json();
  },

  async cancel(jobId: string): Promise<{ message: string }> {
    const response = await fetch(`${API_URL}/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to cancel job: ${response.statusText}`);
    }

    return response.json();
  },

  async getPageResultByNumber(jobId: string, pageNumber: number): Promise<JobResultResponse> {
    // First get all pages to find the job_id for this page number
    const pagesResponse = await this.getPages(jobId);
    const page = pagesResponse.pages.find((p) => p.page_number === pageNumber);

    if (!page) {
      throw new Error(`Page ${pageNumber} not found`);
    }

    // Then get the result for that specific page job
    return this.getResult(page.job_id);
  },

  async delete(jobId: string): Promise<{ message: string }> {
    const response = await fetch(`${API_URL}/jobs/${jobId}`, {
      method: "DELETE",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to delete job: ${response.statusText}`);
    }

    return response.json();
  },

  async retryPage(pageJobId: string): Promise<string> {
    const response = await fetch(`${API_URL}/jobs/${pageJobId}/retry`, {
      method: "POST",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to retry page: ${response.statusText}`);
    }

    const data = await response.json();
    return data.new_job_id || data.job_id;
  },

  getPagePdf(jobId: string, pageNumber: number): string {
    return `${API_URL}/jobs/${jobId}/pages/${pageNumber}/pdf`;
  },
};

// API Keys API
export const apiKeysApi = {
  async list(): Promise<APIKeyInfo[]> {
    const response = await fetch(`${API_URL}/api-keys`, {
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to list API keys: ${response.statusText}`);
    }

    const data = await response.json();
    return data.api_keys || [];
  },

  async create(request: APIKeyCreate): Promise<APIKeyResponse> {
    const response = await fetch(`${API_URL}/api-keys`, {
      method: "POST",
      headers: {
        ...getHeaders(true),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to create API key: ${response.statusText}`);
    }

    return response.json();
  },

  async revoke(keyId: string): Promise<{ message: string }> {
    const response = await fetch(`${API_URL}/api-keys/${keyId}`, {
      method: "DELETE",
      headers: getHeaders(true),
    });

    if (!response.ok) {
      throw new Error(`Failed to revoke API key: ${response.statusText}`);
    }

    return response.json();
  },
};
