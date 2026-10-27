import type { RuntimeStatus } from "@/types/engine-control";

export interface FeatureReplicas {
  feature: string;
  desiredRevision: number;
  /** null when the feature was stopped or cooled down on purpose. */
  desired: number | null;
  appliedRevision: number | null;
  /** "running", "stopped" or "standby" as last applied; null if never applied. */
  mode: string | null;
  /** An operation holds one of the feature's resources right now. */
  busy: boolean;
  alive: number | null;
  ready: number | null;
  observedAt: string | null;
}

type Resource = RuntimeStatus["resources"][number];

const count = (v: unknown) => (typeof v === "number" ? v : null);
const newest = (a: Resource, b: Resource) =>
  (a.observed_at ?? "") < (b.observed_at ?? "") ? 1 : -1;

/**
 * Desired / applied / observed replicas per feature (spec 0007 CA2). Desired
 * comes from the latest saved revision, which may not be applied yet; alive
 * and ready come from the newest observation of a resource whose last applied
 * operation was for that feature, so a shared worker does not lend another
 * feature's counts. No observation yet means unknown (null), never zero.
 */
export function featureReplicas(status: RuntimeStatus | undefined): FeatureReplicas[] {
  if (!status) return [];
  return Object.entries(status.desired).map(([feature, rev]) => {
    const related = status.resources.filter(
      (r) => r.applied?.feature === feature || r.applied?.feature_modes?.[feature],
    );
    const observed = related
      .filter((r) => r.applied?.feature === feature && r.observed_at)
      .sort(newest)[0];
    const moded = related.filter((r) => r.applied?.feature_modes?.[feature]).sort(newest)[0];
    // `applied` is ordered by revision, newest first.
    const appliedRevision =
      status.applied.find((p) => p.feature === feature)?.revision ?? null;
    const mode = moded?.applied?.feature_modes?.[feature] ?? null;
    const stopped =
      appliedRevision === rev.revision && (mode === "stopped" || mode === "standby");
    return {
      feature,
      desiredRevision: rev.revision,
      desired: stopped ? null : rev.profile.desired_replicas,
      appliedRevision,
      mode,
      busy: related.some((r) => r.operation_id != null),
      alive: count(observed?.observed.replicas_alive),
      ready: count(observed?.observed.ready_replicas),
      observedAt: observed?.observed_at ?? null,
    };
  });
}
