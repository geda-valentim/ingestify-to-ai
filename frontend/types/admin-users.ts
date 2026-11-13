import type { IamBinding } from "@/types/iam";

/** GET /admin/users and /admin/users/{id} (spec 0024). Dates are naive UTC ISO-8601. */
export interface AdminUserSummary {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  is_root: boolean;
  created_at: string | null;
  /** Active and not expired. */
  api_keys_active: number;
  projects_total: number;
  /** Top-level jobs only. */
  jobs_total: number;
  jobs_by_status: Record<string, number>;
  bytes_uploaded: number;
  pages_total: number;
  last_job_at: string | null;
  last_api_key_used_at: string | null;
}

export type AdminUserSort = "created_at" | "last_job_at" | "jobs_total" | "bytes_uploaded";

export interface AdminUserListParams {
  q?: string;
  sort?: AdminUserSort;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface AdminUserList {
  total: number;
  /** Jobs whose owner was deleted. */
  orphan_jobs: number;
  items: AdminUserSummary[];
}

export interface AdminUserApiKey {
  id: string;
  name: string | null;
  is_active: boolean;
  created_at: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  expired: boolean;
  project_id: string | null;
}

export interface AdminUserProject {
  id: string;
  name: string;
  archived: boolean;
  created_at: string | null;
  folder_count: number;
  jobs_total: number;
}

export interface AdminUserDetail extends AdminUserSummary {
  api_keys: AdminUserApiKey[];
  projects: AdminUserProject[];
  usage: {
    by_source_type: Record<string, number>;
    last_30_days: { jobs: number; bytes: number; pages: number };
  };
  iam_bindings: IamBinding[];
}
