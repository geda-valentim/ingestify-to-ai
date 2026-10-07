import { controlRequest as request } from "./engine-control-api";
import type {
  AccessInfo,
  ExecutionProfile,
  AccessPolicy,
  InstallationPrincipal,
  ResourceScope,
} from "@/types/access";
const base = "/admin/execution-profiles";
export const accessApi = {
  me: () => request<AccessInfo>("/admin/access/me"),
  profiles: () => request<ExecutionProfile[]>(base),
  profile: (id: string) => request<ExecutionProfile>(`${base}/${id}`),
  create: (body: unknown) => request<ExecutionProfile>(base, "POST", body),
  revise: (id: string, body: unknown) =>
    request<ExecutionProfile>(`${base}/${id}/revisions`, "POST", body),
  metadata: (id: string, body: unknown) =>
    request<ExecutionProfile>(`${base}/${id}`, "PUT", body),
  publish: (p: ExecutionProfile, revision_id: string) =>
    request<ExecutionProfile>(`${base}/${p.id}/publish`, "POST", {
      version: p.version,
      revision_id,
    }),
  archive: (p: ExecutionProfile) =>
    request<ExecutionProfile>(`${base}/${p.id}/archive`, "POST", {
      version: p.version,
    }),
  bind: (
    engine: string,
    feature: string,
    version: number,
    revision_id: string,
  ) =>
    request(`/admin/engines/${engine}/runtime-profile/bind`, "POST", {
      feature,
      version,
      revision_id,
    }),
  import: (engine: string, body: unknown) =>
    request<ExecutionProfile>(
      `/admin/engines/${engine}/runtime-profile/import`,
      "POST",
      body,
    ),
  hosts: () =>
    request<{ id: string; services: string[] }[]>(
      "/admin/execution-profile-hosts",
    ),
  policies: () => request<AccessPolicy[]>("/admin/access/policies"),
  createPolicy: (body: unknown) =>
    request<AccessPolicy>("/admin/access/policies", "POST", body),
  revisePolicy: (p: AccessPolicy, constraints: unknown) =>
    request<AccessPolicy>(`/admin/access/policies/${p.id}/revisions`, "POST", {
      version: p.version,
      constraints,
    }),
  subjects: () =>
    request<{ id: string; username: string; email: string }[]>(
      "/admin/access/subjects",
    ),
  attributes: () =>
    request<{ engine_id: string; environment: string; version: number }[]>(
      "/admin/access/engine-attributes",
    ),
  classify: (id: string, environment: string, version: number) =>
    request(`/admin/access/engine-attributes/${id}`, "PUT", {
      environment,
      version,
    }),
  resources: () => request<ResourceScope[]>("/admin/access/resources"),
  qualify: (body: ResourceScope) =>
    request<ResourceScope>("/admin/access/resources", "PUT", {
      key: body.key,
      version: body.version,
      consumers: body.consumers,
      qualified: body.qualified,
    }),
  principals: () =>
    request<InstallationPrincipal[]>("/admin/access/installation-principals"),
  registerPrincipal: (id: string) =>
    request<InstallationPrincipal>(
      "/admin/access/installation-principals",
      "POST",
      { id },
    ),
  setPrincipal: (p: InstallationPrincipal, active: boolean) =>
    request<InstallationPrincipal>(
      `/admin/access/installation-principals/${encodeURIComponent(p.id)}`,
      "PUT",
      { version: p.version, active },
    ),
};
