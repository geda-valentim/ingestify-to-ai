import type { RuntimeStatus } from "@/types/engine-control";

export interface FeatureReplicas {
  feature: string;
  desiredRevision: number;
  desired: number;
  /** null when no applied revision is visible to this user. */
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
 * is always the latest saved revision, which may not be applied yet; the
 * applied revision is the one applied last (the API's rule, so a rollback to
 * an older revision counts), with its mode. Alive and ready come from the
 * newest observation of a resource whose last applied operation was for that
 * feature, so a shared worker does not lend another feature's counts. No
 * observation yet means unknown (null), never zero.
 */
export function featureReplicas(status: RuntimeStatus | undefined): FeatureReplicas[] {
  if (!status) return [];
  return Object.entries(status.desired).map(([feature, rev]) => {
    const related = status.resources.filter(
      (r) => r.applied?.feature === feature || r.applied?.feature_modes?.[feature],
    );
    const own = related.filter((r) => r.applied?.feature === feature).sort(newest);
    const observed = own.find((r) => r.observed_at);
    const moded =
      own.find((r) => r.applied?.feature_modes?.[feature]) ??
      related.filter((r) => r.applied?.feature_modes?.[feature]).sort(newest)[0];
    const applied = status.applied
      .filter((p) => p.feature === feature && p.applied_at)
      .sort((a, b) =>
        a.applied_at === b.applied_at
          ? b.revision - a.revision
          : a.applied_at! < b.applied_at!
            ? 1
            : -1,
      )[0];
    return {
      feature,
      desiredRevision: rev.revision,
      desired: rev.profile.desired_replicas,
      appliedRevision: applied?.revision ?? null,
      mode: moded?.applied?.feature_modes?.[feature] ?? null,
      busy: related.some((r) => r.operation_id != null),
      alive: count(observed?.observed.replicas_alive),
      ready: count(observed?.observed.ready_replicas),
      observedAt: observed?.observed_at ?? null,
    };
  });
}

/**
 * An operation holds a resource that was never applied for any feature (the
 * feature's first operation): runtime-status does not say which feature it
 * is for, so it can only be flagged for the whole engine.
 */
export function unattributedBusy(status: RuntimeStatus | undefined): boolean {
  return !!status?.resources.some(
    (r) =>
      r.operation_id != null &&
      !r.applied?.feature &&
      !Object.keys(r.applied?.feature_modes ?? {}).length,
  );
}

const modeLabel: Record<string, string> = { stopped: "parada", standby: "standby" };

/** The applied column: revision in force, its mode and any unapplied save. */
export function appliedLabel(r: FeatureReplicas): string {
  const mode = r.mode && modeLabel[r.mode] ? ` (${modeLabel[r.mode]})` : "";
  // Applied on a resource, but the revision is hidden from this user: it
  // cannot be compared with the saved one.
  if (r.appliedRevision == null && r.mode != null) return `não visível${mode}`;
  const applied =
    r.appliedRevision != null ? `revisão ${r.appliedRevision}${mode}` : "nenhuma";
  return r.appliedRevision === r.desiredRevision
    ? applied
    : `${applied} · revisão ${r.desiredRevision} salva, não aplicada`;
}
