import type { RuntimeProfile } from "./engine-control";
export interface AccessInfo {
  enabled: boolean;
  bootstrap: boolean;
  permissions: string[];
}
export interface ExecutionRevision {
  id: string;
  revision: number;
  settings: RuntimeProfile;
  warm_for_seconds: number | null;
  content_hash: string;
  model_fingerprint: string;
  published_at: string | null;
}
export interface ExecutionProfile {
  id: string;
  name: string;
  description: string;
  adapter_type: string;
  feature: string;
  environment: string;
  status: string;
  version: number;
  latest_published_revision_id: string | null;
  permissions: string[];
  revisions?: ExecutionRevision[];
  bindings?: {
    engine_id: string;
    feature: string;
    revision: number;
    applied_at: string | null;
  }[];
}
export interface Constraints {
  engine_ids: string[];
  profile_ids: string[] | null;
  adapters: string[];
  features: string[];
  environments: string[];
  host_ids: string[] | null;
  gpu_uuids: string[] | null;
  model_ids: string[] | null;
  max_replicas: number;
  max_concurrency: number;
  max_cpu: number;
  max_memory_mb: number;
  max_warm_seconds: number;
  max_usd: string;
}
export interface AccessPolicy {
  id: string;
  name: string;
  version: number;
  revisions: { id: string; revision: number; constraints: Constraints }[];
}
/** An `installation:<name>` OS principal of the direct CLI (0009). */
export interface InstallationPrincipal {
  id: string;
  active: boolean;
  version: number;
  purpose: string;
}
export interface ResourceScope {
  key: string;
  owner_engine_id: string;
  version: number;
  consumers: { engine_id: string; feature: string }[];
  qualified: boolean;
}
