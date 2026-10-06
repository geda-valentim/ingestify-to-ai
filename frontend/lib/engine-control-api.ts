import { API_URL, ApiError, apiFetch, getHeaders } from "./api";
import type {
  Capabilities,
  ModelProfile,
  RuntimeProfile,
  ProfileRevision,
  ControlPlan,
  Operation,
  OperationEvent,
  RuntimeStatus,
} from "@/types/engine-control";

export async function controlRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
  extra?: Record<string, string>,
): Promise<T> {
  const r = await apiFetch(`${API_URL}${path}`, {
    method,
    headers: {
      ...getHeaders(true),
      "Content-Type": "application/json",
      ...extra,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || detail?.code || `Erro ${r.status}`;
    throw new ApiError(r.status, data, message);
  }
  return data as T;
}
const engine = (id: string) => `/admin/engines/${encodeURIComponent(id)}`;
export const engineControlApi = {
  capabilities: (id: string) =>
    controlRequest<Capabilities>(`${engine(id)}/capabilities`),
  adapters: () =>
    controlRequest<Capabilities[]>("/admin/engine-control-adapters"),
  models: () => controlRequest<ModelProfile[]>("/admin/model-profiles"),
  create: (body: {
    adapter_type: string;
    display_name: string;
    slug: string;
  }) => controlRequest<{ id: string }>("/admin/engines", "POST", body),
  profile: (id: string, feature: string) =>
    controlRequest<ProfileRevision | null>(
      `${engine(id)}/runtime-profile?feature=${encodeURIComponent(feature)}`,
    ),
  save: (
    id: string,
    feature: string,
    version: number,
    profile: RuntimeProfile,
  ) =>
    controlRequest<ProfileRevision>(`${engine(id)}/runtime-profile`, "PUT", {
      feature,
      version,
      profile,
    }),
  status: (id: string) =>
    controlRequest<RuntimeStatus>(`${engine(id)}/runtime-status`),
  plan: (id: string, body: unknown) =>
    controlRequest<ControlPlan>(`${engine(id)}/operation-plans`, "POST", body),
  execute: (id: string, plan: ControlPlan, key: string) =>
    controlRequest<Operation>(
      `${engine(id)}/operations`,
      "POST",
      {
        plan_id: plan.plan_id,
        plan_hash: plan.plan_hash,
        confirm_paid_operation: true,
      },
      { "Idempotency-Key": key },
    ),
  history: (id: string) =>
    controlRequest<{ operations: Operation[] }>(
      `/admin/engine-operations?engine_id=${encodeURIComponent(id)}`,
    ),
  snapshot: (op: string) =>
    controlRequest<Operation>(`/admin/engine-operations/${op}`),
  events: (op: string, after: number) =>
    controlRequest<{
      events: OperationEvent[];
      next: number;
      has_more: boolean;
      state: string;
    }>(`/admin/engine-operations/${op}/events?after=${after}`),
  cancel: (op: string) =>
    controlRequest<Operation>(`/admin/engine-operations/${op}/cancel`, "POST"),
  recover: (op: string) =>
    controlRequest<Operation>(`/admin/engine-operations/${op}/recover`, "POST"),
  quick: (
    id: string,
    action: string,
    version: number,
    body: Record<string, unknown> = {},
  ) =>
    controlRequest<unknown>(
      `${engine(id)}/${action}`,
      ["budget", "credentials", "gpus"].includes(action) ? "PUT" : "POST",
      { version, ...body },
    ),
};
