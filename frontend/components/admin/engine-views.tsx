"use client";

import { AlertTriangle, CheckCircle2, Cloud, KeyRound, Server, Wallet } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Engine, Feature, FeatureCapacity } from "@/types/compute";
import {
  CommandHint,
  DeployStateBadge,
  ENGINES_CLI,
  ENGINES_CLI_REMOTE,
  HealthBadge,
  Meter,
  Pill,
  StatusBadge,
  featureTitle,
  formatAgo,
  formatUsd,
} from "@/components/admin/compute-ui";

export function isLocal(engine: Pick<Engine, "adapter_type">) {
  return engine.adapter_type === "local";
}

export function EngineIcon({ engine, className }: { engine: Pick<Engine, "adapter_type">; className?: string }) {
  const Icon = isLocal(engine) ? Server : Cloud;
  return <Icon className={cn("h-5 w-5 text-muted-foreground", className)} aria-hidden />;
}

export function adapterLabel(adapter: string) {
  if (adapter === "local") return "This server";
  if (adapter === "modal") return "Modal";
  return adapter;
}

/** "L4 GPU", "GPU gpu0", "CPU" */
function bindingDevice(engine: Engine, cap: FeatureCapacity) {
  const b = cap.binding;
  if (b.gpu_type) return `${b.gpu_type} GPU`;
  if (b.gpu_ref) {
    const gpu = (engine.config.gpus ?? []).find((g) => g.ref === b.gpu_ref);
    return gpu?.name ? `${gpu.name} (${b.gpu_ref})` : `GPU ${b.gpu_ref}`;
  }
  return "CPU";
}

/** The CLI line that would set this binding as it is now, as a template to edit. */
export function setCapacityCommand(engine: Engine, feature: Feature, cap?: FeatureCapacity) {
  const b = cap?.binding;
  const parts = [`${ENGINES_CLI} set-capacity ${engine.slug} ${feature}`, `--workers ${b?.workers ?? 1}`];
  if (b && b.executions_per_worker !== 1) parts.push(`--executions-per-worker ${b.executions_per_worker}`);
  if (isLocal(engine)) {
    if (b?.gpu_ref) parts.push(`--gpu-ref ${b.gpu_ref}`);
    else if (!b) parts.push("--gpu-ref gpu0");
  } else {
    parts.push(`--gpu-type ${b?.gpu_type ?? "L4"}`);
  }
  return parts.join(" ");
}

/** One feature's binding on an engine: device, capacity vs in flight, replicas or deploy. */
export function FeatureCapacityRow({
  engine,
  feature,
  cap,
  showCommands = false,
}: {
  engine: Engine;
  feature: Feature;
  cap: FeatureCapacity;
  showCommands?: boolean;
}) {
  const local = isLocal(engine);
  const configured = cap.workers_configured ?? cap.binding.workers;
  const alive = cap.workers_alive;
  const short = local && alive !== undefined && alive < configured;

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium text-sm">{featureTitle(feature)}</p>
          <p className="text-xs text-muted-foreground">
            {bindingDevice(engine, cap)} · {cap.binding.workers} {local ? "replica" : "container"}
            {cap.binding.workers === 1 ? "" : "s"} × {cap.binding.executions_per_worker} at a time
            {cap.binding.vram_override_gb ? ` · ${cap.binding.vram_override_gb} GB each (override)` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {local && alive !== undefined && (
            <Pill
              tone={alive === 0 && configured > 0 ? "bad" : short ? "warn" : "ok"}
              icon={short ? AlertTriangle : CheckCircle2}
              title="Replicas declared on the engine vs worker heartbeats seen in the last minutes"
            >
              configured {configured}, alive {alive}
            </Pill>
          )}
          <DeployStateBadge state={cap.deploy_state} />
        </div>
      </div>
      <Meter
        label="In flight / capacity"
        value={cap.in_flight}
        max={cap.capacity}
        valueText={`${cap.in_flight} of ${cap.capacity}`}
      />
      {showCommands && (
        <CommandHint
          commands={
            local
              ? [setCapacityCommand(engine, feature, cap), ...(cap.scale_hint ? [cap.scale_hint] : [])]
              : [
                  setCapacityCommand(engine, feature, cap),
                  `${ENGINES_CLI_REMOTE} modal-deploy --engine ${engine.slug} --feature ${feature}`,
                ]
          }
          note={
            local
              ? "The first line records the capacity (validated against VRAM); the second starts that many replicas."
              : "A capacity change takes effect only after the deploy; until then the binding takes no new work."
          }
        />
      )}
      {!showCommands && short && cap.scale_hint && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Fewer replicas alive than configured. Start them with <code className="font-mono">{cap.scale_hint}</code>
        </p>
      )}
      {!showCommands && cap.deploy_state === "needs_redeploy" && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          The binding changed since the last deploy; it takes no new work until{" "}
          <code className="font-mono">engines.py modal-deploy --engine {engine.slug}</code> runs.
        </p>
      )}
    </div>
  );
}

export function BudgetSummary({ engine, compact = false }: { engine: Engine; compact?: boolean }) {
  const b = engine.budget;
  if (isLocal(engine)) {
    return <p className="text-sm text-muted-foreground">No cost: runs on this server.</p>;
  }
  if (b.limit_usd === null) {
    return (
      <p className="text-sm flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
        <Wallet className="h-4 w-4" aria-hidden />
        No budget set: the engine cannot be activated without one.
      </p>
    );
  }
  return (
    <div className="text-sm space-y-0.5">
      <p className="flex items-center gap-1.5">
        <Wallet className="h-4 w-4 text-muted-foreground" aria-hidden />
        <span>
          Limit <span className="font-medium">{formatUsd(b.limit_usd)}</span> per period
        </span>
      </p>
      {!compact && (
        <p className="text-xs text-muted-foreground">
          Warn at {b.soft_pct ?? "—"} % · keep {formatUsd(b.min_remaining_usd)} in reserve · period starts on day{" "}
          {b.period_anchor_day ?? 1} ({b.period_tz ?? "UTC"})
        </p>
      )}
      <p className="text-xs text-muted-foreground">Spend so far is not exposed by the API yet.</p>
    </div>
  );
}

export function CredentialsSummary({ engine }: { engine: Engine }) {
  if (isLocal(engine)) return null;
  const fields = Object.entries(engine.credentials);
  if (fields.length === 0) {
    return (
      <p className="text-sm flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
        <KeyRound className="h-4 w-4" aria-hidden />
        No credentials stored
      </p>
    );
  }
  return (
    <div className="text-sm flex flex-wrap items-center gap-x-3 gap-y-1">
      <KeyRound className="h-4 w-4 text-muted-foreground" aria-hidden />
      {fields.map(([name, state]) => (
        <span key={name}>
          <span className="text-muted-foreground">{name}</span>{" "}
          <span className="font-medium">
            {state.is_set ? (state.hint ? `set (…${state.hint})` : "set") : "not set"}
          </span>
        </span>
      ))}
      {engine.credentials_updated_at && (
        <span className="text-xs text-muted-foreground">changed {formatAgo(engine.credentials_updated_at)}</span>
      )}
    </div>
  );
}

export function EngineBadges({ engine }: { engine: Engine }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatusBadge status={engine.status} />
      <HealthBadge health={engine.health} reason={engine.health_reason} />
    </div>
  );
}
