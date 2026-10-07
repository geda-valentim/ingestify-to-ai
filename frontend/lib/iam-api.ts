import { controlRequest as request } from "./engine-control-api";
import type { IamBinding, IamBindingCreate, IamCatalog } from "@/types/iam";
const base = "/admin/iam/bindings";
export const iamApi = {
  catalog: () => request<IamCatalog>("/iam/permissions"),
  bindings: (includeInactive = false) =>
    request<{ bindings: IamBinding[] }>(
      `${base}${includeInactive ? "?include_inactive=true" : ""}`,
    ).then((r) => r.bindings),
  grant: (body: IamBindingCreate) =>
    request<IamBinding>(base, "POST", body),
  revoke: (b: IamBinding) =>
    request<IamBinding>(`${base}/${encodeURIComponent(b.id)}/revoke`, "POST", {
      version: b.version,
    }),
};
