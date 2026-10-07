import type { Binding } from "./compute";
export interface ControlField {
  name: string;
  label: string;
  type: "number" | "text" | "secret" | "select";
  min?: number;
  max?: number;
  options?: { value: string; label: string }[];
}
export interface Capabilities {
  type: string;
  title: string;
  managed: boolean;
  execution_mode: string;
  create_connection: boolean;
  requires_budget: boolean;
  fields: ControlField[];
  provider_fields: ControlField[];
  credential_fields: ControlField[];
  features: string[];
  actions: {
    type: string;
    supported: boolean;
    enabled: boolean;
    reason: string | null;
    /** Portuguese explanation of `reason` (null when enabled). */
    message?: string | null;
    next_steps?: string[];
  }[];
  hosts: { id: string; services: string[] }[];
  requires_control_identity?: boolean;
  /** 0009 CA1: what is missing before operating the selected feature. */
  setup?: {
    feature: string | null;
    code: string | null;
    profile_bound: boolean;
    /** null when the adapter has no provider identity to verify. */
    connection_verified: boolean | null;
    message: string | null;
    next_steps: string[];
  };
}
export interface ModelProfile {
  id: string;
  title: string;
  feature: string;
  adapters: string[];
  approved: boolean;
  footprint_gb: number | null;
  model: string;
}
export interface RuntimeProfile {
  adapter_version: number;
  schema_version: number;
  binding: Binding;
  model_profile_id: string;
  desired_replicas: number;
  max_replicas: number;
  min_ready_replicas: number;
  idle_timeout_seconds: number;
  memory_mb?: number | null;
  warmup_mode: "on_start" | "manual";
  warm_until: string | null;
  provider_settings: Record<string, unknown>;
}
export interface ProfileRevision {
  id: string;
  feature: string;
  revision: number;
  profile: RuntimeProfile;
  applied_at: string | null;
  source_profile_revision_id?: string | null;
  source_hash?: string | null;
}
export interface ControlPlan {
  plan_id: string;
  plan_hash: string;
  type: string;
  estimated_max_usd: string;
  destructive: boolean;
  resources: string[];
  stages: string[];
  effects: string[];
  expires_at: string;
  profile_revision: number | null;
}
export interface Operation {
  operation_id: string;
  state: string;
  stage: string;
  can_cancel: boolean;
  can_recover?: boolean;
  last_seq: number;
  error: {
    code?: string;
    message?: string;
    human_message?: string;
    next_steps?: string[];
  } | null;
  result: Record<string, unknown>;
  created_at: string;
  reserved_usd: string;
  actual_usd: string | null;
  cost_confirmed: boolean;
}
export interface OperationEvent {
  seq: number;
  type: string;
  stage: string;
  payload: { message?: string; result?: unknown; error?: unknown };
  at: string;
}
export interface RuntimeStatus {
  desired: Record<string, ProfileRevision>;
  applied: ProfileRevision[];
  resources: {
    key: string;
    maintenance: boolean;
    operation_id: string | null;
    observed_at: string | null;
    observed: Record<string, unknown>;
  }[];
}
