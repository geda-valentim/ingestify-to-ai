import { controlRequest as request } from "./engine-control-api";
import type {
  AdminUserDetail,
  AdminUserList,
  AdminUserListParams,
} from "@/types/admin-users";

/** Read-only user directory (spec 0024): `platform.users.read`. */
export const adminUsersApi = {
  list: (params: AdminUserListParams = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    const qs = query.toString();
    return request<AdminUserList>(`/admin/users${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) =>
    request<AdminUserDetail>(`/admin/users/${encodeURIComponent(id)}`),
};
