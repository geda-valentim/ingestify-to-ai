/**
 * Execution engines, capacity and routing (spec 0003) as the admin API returns them.
 *
 * Mirrors the real backend payloads, not Appendix C of the spec, which differs:
 *   - engine:   backend/shared/engines/store.py `engine_view`
 *   - adapters: backend/api/engine_admin_routes.py `list_engine_adapters`
 *   - gpus:     backend/api/engine_admin_routes.py `list_gpus`
 *   - routing:  backend/shared/engines/routing.py `describe` + `_backlog`
 *   - status:   backend/api/routing_admin_routes.py `engines_status`
 * Read-only in v1 (spec 0003, 4.6.8): nothing here is ever written by the UI.
 */

export type Feature = "transcription" | "document_conversion" | "vision";
export type AdapterType = "local" | "modal" | (string & {});
export type EngineStatus = "active" | "paused" | "disabled";
export type EngineHealth = "unknown" | "healthy" | "degraded" | "unhealthy" | "exhausted";
/** `local` always runs what is configured; a remote binding must match its deploy. */
export type DeployState = "local" | "deployed" | "not_deployed" | "needs_redeploy";
/** `GET /jobs/{id}`: where the job runs, never which engine (spec S18). */
export type EngineKind = "local" | "cloud";
export type QueueReason = "in_queue" | "starting";

/** How a feature runs on an engine (backend `capacity.Binding`, None fields omitted). */
export interface Binding {
  gpu_type?: string; // remote, e.g. "L4"
  gpu_ref?: string; // local: a declared physical GPU; absent = CPU
  workers: number;
  executions_per_worker: number;
  cpu?: number;
  vram_override_gb?: number;
}

export interface FeatureCapacity {
  binding: Binding;
  capacity: number;
  in_flight: number;
  deploy_state: DeployState;
  // remote only
  deployed_fingerprint?: string | null;
  expected_fingerprint?: string | null;
  deployed_at?: string | null;
  // local only
  workers_alive?: number;
  workers_configured?: number;
  scale_hint?: string;
}

export interface EngineBudget {
  limit_usd: number | null;
  min_remaining_usd: number | null;
  soft_pct: number | null;
  period_tz: string | null;
  period_anchor_day: number | null;
}

/** One credential field, masked: whether it is set and at most its last 4 characters. */
export interface CredentialState {
  is_set: boolean;
  hint: string | null;
}

export interface VramBudgetLine {
  gpu: string;
  vram_gb: number;
  budgeted_gb: number;
  fits: boolean;
  terms: string[];
}

export interface LocalGpuDeclared {
  ref: string;
  name?: string;
  uuid?: string | null;
  vram_gb: number;
  vram_reserve_gb?: number;
}

export interface EngineLastTest {
  ok: boolean;
  code: string | null;
  at: string;
  deployed?: boolean;
  detail?: string;
}

/** `config` minus `features`; the keys depend on the adapter. */
export interface EngineConfig {
  gpus?: LocalGpuDeclared[];
  last_test?: EngineLastTest;
  account_max_gpus?: number;
  max_input_bytes?: number;
  [key: string]: unknown;
}

export interface Engine {
  id: string;
  slug: string;
  display_name: string;
  adapter_type: AdapterType;
  status: EngineStatus;
  health: EngineHealth;
  health_reason: string | null;
  is_system: boolean;
  version: number;
  budget: EngineBudget;
  credentials: Record<string, CredentialState>;
  credentials_updated_at: string | null;
  config: EngineConfig;
  features: Partial<Record<Feature, FeatureCapacity>>;
  gpu_budget: VramBudgetLine[];
  config_error: { message: string; lines: string[] } | null;
  updated_at: string | null;
}

export interface ModalGpuOption {
  gpu_type: string;
  vram_gb: number;
  usd_per_second: number;
  usd_per_hour: number;
}

export interface AdapterDescriptor {
  type: AdapterType;
  features: Feature[];
  feature_info: Partial<Record<Feature, { title: string; vram_per_execution_gb: number }>>;
  /** local: a sentence; modal: the GPUs on offer with their prices */
  gpu_options: string | ModalGpuOption[];
  prices_as_of?: string;
  prices_verified?: boolean;
  account_max_gpus_default?: number;
  max_executions_per_worker: number | { gpu: number; cpu: number | null };
  vram_reserve_gb: number;
}

export interface PhysicalGpu {
  ref: string;
  name: string;
  uuid: string | null;
  vram_gb: number;
  reserve_gb: number;
  budgeted_gb: number;
  live_reserved_gb?: number;
  used_gb: number | null;
  detected: boolean;
  bindings: { feature: Feature; workers: number; executions_per_worker: number; vram_each_gb: number }[];
}

export interface DetectedGpu {
  uuid: string;
  name: string | null;
  vram_total_gb: number;
  vram_used_gb: number;
  workers: { feature: Feature | "live-transcription"; hostname: string }[];
}

export interface GpusResponse {
  declared: PhysicalGpu[];
  undeclared_detected: DetectedGpu[];
  live_worker?: { ready: boolean; capacity: number; resident_vram_gb: number; model: string; backend: string } | null;
}

export interface RouteStepEngine {
  id: string;
  slug: string | null;
  adapter_type: AdapterType | null;
}

export interface RouteStep {
  position?: number | null;
  engine_ids: string[];
  engines: RouteStepEngine[];
  group_strategy: "priority" | "fill_first";
  scale_out_after_seconds?: number | null;
  when?: { min_wait_seconds?: number | null; min_backlog?: number | null } | null;
  /** usd is a Decimal: it may arrive as a string */
  spend_cap?: { usd: number | string; window: "day" | "period" } | null;
}

export type BacklogState = "probing" | "waiting" | "assigned" | "running" | "bypassed" | "done" | "failed";

export interface Backlog {
  waiting: number;
  by_state: Record<BacklogState, number>;
  oldest_wait_seconds: number | null;
  bypassed_24h: number;
  fallback_in_flight: number;
}

interface FeatureRouteBase {
  feature: Feature;
  state: "active" | "draining";
  steps: RouteStep[];
  version: number;
  updated_at: string | null;
  updated_by: string | null;
  backlog?: Backlog;
}

/** No route: today's path (the feature's own queue, no backlog, no dispatcher). */
export interface ImplicitRoute extends FeatureRouteBase {
  implicit: true;
  description: string;
}

export interface ExplicitRoute extends FeatureRouteBase {
  implicit: false;
  on_no_engine: "hold" | "fail";
  fail_after_seconds: number | null;
  max_attempts: number;
  remote_allowed_for: "admins" | "all";
  user_period_limit_usd: number | null;
  remote_data_notice: string | null;
  dispatcher_fallback: "local_direct" | "hold";
  dispatcher_down_seconds: number;
}

export type FeatureRoute = ImplicitRoute | ExplicitRoute;

export interface DispatcherLease {
  epoch: number;
  holder: string | null;
  holder_kind: string | null;
  renewed_at: string | null;
  dispatcher_seen_at: string | null;
  dispatcher_seen_seconds_ago: number | null;
}

export interface EngineCapacityRow {
  engine: string; // slug
  adapter_type: AdapterType;
  feature: Feature;
  status: EngineStatus;
  health: EngineHealth;
  capacity: number;
  in_flight: number;
  fallback_in_flight: number;
  workers_configured?: number;
  workers_alive?: number | null;
}

/** worker-remote's heartbeat; Redis hash, so every value is a string. */
export interface RemoteWorkerHeartbeat {
  hostname?: string;
  concurrency?: string;
  private_keys?: "yes" | "no";
  updated_at?: string; // epoch seconds
}

export interface EnginesStatus {
  dispatcher: DispatcherLease;
  engines: EngineCapacityRow[];
  backlog: Record<Feature, Backlog>;
  remote_worker: RemoteWorkerHeartbeat | null;
}

export const FEATURE_TITLES: Record<Feature, string> = {
  transcription: "Transcription",
  document_conversion: "Document conversion",
  vision: "Image analysis",
};

export const FEATURES: Feature[] = ["transcription", "document_conversion", "vision"];
