import type { RuntimeStatus } from "@/types/engine-control";

export interface FeatureReplicas {
  feature: string;
  desiredRevision: number;
  desired: number;
  alive: number | null;
  ready: number | null;
  observedAt: string | null;
}

const count = (v: unknown) => (typeof v === "number" ? v : null);

/**
 * Desired / alive / ready replicas per feature (spec 0007 CA2). The desired
 * count comes from the latest profile revision; alive and ready come from the
 * newest observation of a resource whose last applied operation was for that
 * feature, so a shared worker never lends another feature's counts. No
 * observation yet means unknown (null), never zero.
 */
export function featureReplicas(status: RuntimeStatus | undefined): FeatureReplicas[] {
  if (!status) return [];
  return Object.entries(status.desired).map(([feature, rev]) => {
    const observed = status.resources
      .filter((r) => r.applied?.feature === feature && r.observed_at)
      .sort((a, b) => (a.observed_at! < b.observed_at! ? 1 : -1))[0];
    return {
      feature,
      desiredRevision: rev.revision,
      desired: rev.profile.desired_replicas,
      alive: count(observed?.observed.replicas_alive),
      ready: count(observed?.observed.ready_replicas),
      observedAt: observed?.observed_at ?? null,
    };
  });
}
