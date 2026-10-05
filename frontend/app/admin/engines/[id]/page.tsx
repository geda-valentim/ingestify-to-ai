"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, XCircle } from "lucide-react";
import { ApiError, computeApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { formatBytes } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CommandHint,
  ENGINES_CLI,
  ENGINES_CLI_REMOTE,
  Freshness,
  LoadingCards,
  Meter,
  Pill,
  QueryError,
  adminRetry,
  formatAgo,
} from "@/components/admin/compute-ui";
import {
  BudgetSummary,
  CredentialsSummary,
  EngineBadges,
  EngineIcon,
  FeatureCapacityRow,
  adapterLabel,
  isLocal,
  setCapacityCommand,
} from "@/components/admin/engine-views";
import type { Engine, Feature } from "@/types/compute";

export default function EngineDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const token = useAuthStore((s) => s.token);
  const query = useQuery({
    queryKey: ["admin", "engine", id, token],
    queryFn: () => computeApi.engine(id),
    enabled: !!token,
    refetchInterval: 10_000,
    retry: adminRetry,
  });

  const back = (
    <Link href="/admin/engines" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4 mr-1" aria-hidden />
      All engines
    </Link>
  );

  if (query.isLoading) return <LoadingCards count={3} label="Loading engine" />;
  if (query.error && !query.data) {
    if (query.error instanceof ApiError && query.error.status === 404) {
      return (
        <div className="space-y-4">
          {back}
          <Card>
            <CardContent className="pt-6 text-sm">
              No engine <code className="font-mono">{id}</code>.
            </CardContent>
          </Card>
        </div>
      );
    }
    return <QueryError error={query.error} what="the engine" onRetry={() => query.refetch()} />;
  }
  const engine = query.data!;
  const local = isLocal(engine);
  const features = Object.entries(engine.features) as [Feature, NonNullable<Engine["features"][Feature]>][];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {back}
        <Freshness updatedAt={query.dataUpdatedAt} fetching={query.isFetching} />
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <EngineIcon engine={engine} className="mt-1 h-6 w-6" />
              <div className="min-w-0">
                <CardTitle className="text-2xl">{engine.display_name}</CardTitle>
                <CardDescription>
                  <code className="font-mono">{engine.slug}</code> · {adapterLabel(engine.adapter_type)} · version{" "}
                  {engine.version} · changed {formatAgo(engine.updated_at)}
                </CardDescription>
              </div>
            </div>
            <EngineBadges engine={engine} />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {engine.health_reason && (
            <p className="text-sm">
              <span className="font-medium">Health reason: </span>
              <span className="text-muted-foreground">{engine.health_reason}</span>
            </p>
          )}
          {local ? (
            <p className="text-sm text-muted-foreground">
              The built-in engine: this server&apos;s own workers. Always active; it cannot be paused.
            </p>
          ) : (
            <CommandHint
              title="Lifecycle"
              commands={[
                engine.status === "active" ? `${ENGINES_CLI} pause ${engine.slug}` : `${ENGINES_CLI} activate ${engine.slug}`,
                `${ENGINES_CLI_REMOTE} test --engine ${engine.slug}`,
              ]}
              note="Activation needs a passing test newer than the credentials, a budget, a verified deploy and executions_per_worker = 1. Pausing lets work in flight finish."
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Capacity per feature</CardTitle>
          <CardDescription>
            {local
              ? "Replicas declared here vs worker heartbeats; capacity = replicas × executions at a time."
              : "Containers × executions per container; the deployed app must match the binding."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {features.length === 0 && (
            <>
              <p className="text-sm text-muted-foreground">No feature bound to this engine.</p>
              <CommandHint commands={[setCapacityCommand(engine, "transcription")]} />
            </>
          )}
          {features.map(([feature, cap]) => (
            <div key={feature} className="space-y-1">
              <FeatureCapacityRow engine={engine} feature={feature} cap={cap} showCommands />
              {!local && (cap.deployed_fingerprint || cap.expected_fingerprint) && (
                <p className="text-xs text-muted-foreground px-1">
                  Deployed fingerprint <code className="font-mono">{cap.deployed_fingerprint ?? "none"}</code>
                  {cap.expected_fingerprint && cap.expected_fingerprint !== cap.deployed_fingerprint && (
                    <>
                      {" "}· a deploy now would ship <code className="font-mono">{cap.expected_fingerprint}</code>
                    </>
                  )}
                  {cap.deployed_at && <> · verified {formatAgo(cap.deployed_at)}</>}
                </p>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      {(engine.gpu_budget.length > 0 || engine.config_error) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">VRAM budget</CardTitle>
            <CardDescription>
              {local ? "Per physical GPU, summed over every feature on it." : "Per container GPU of each binding."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {engine.config_error && (
              <div role="alert" className="rounded-md border border-red-600/30 bg-red-500/10 p-3 text-sm space-y-1">
                <p className="flex items-center gap-1.5 font-medium text-red-700 dark:text-red-400">
                  <AlertTriangle className="h-4 w-4" aria-hidden />
                  {engine.config_error.message}
                </p>
                {engine.config_error.lines.map((line) => (
                  <p key={line} className="font-mono text-xs text-muted-foreground">
                    {line}
                  </p>
                ))}
              </div>
            )}
            {engine.gpu_budget.map((line) => (
              <div key={line.gpu} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{line.gpu}</span>
                  {line.fits ? (
                    <Pill tone="ok" icon={CheckCircle2}>fits</Pill>
                  ) : (
                    <Pill tone="bad" icon={XCircle}>does not fit</Pill>
                  )}
                </div>
                <Meter
                  label="Budgeted VRAM (reserve included)"
                  value={line.budgeted_gb}
                  max={line.vram_gb}
                  valueText={`${line.budgeted_gb} of ${line.vram_gb} GB`}
                />
                {line.terms.length > 0 && (
                  <p className="text-xs text-muted-foreground">{line.terms.join(" + ")}</p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {local ? (
        <LocalGpusCard engine={engine} />
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Budget and credentials</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <BudgetSummary engine={engine} />
            <CredentialsSummary engine={engine} />
            <LastTest engine={engine} />
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {engine.config.account_max_gpus !== undefined && (
                <>
                  <dt className="text-muted-foreground">Account GPU limit</dt>
                  <dd>{String(engine.config.account_max_gpus)}</dd>
                </>
              )}
              {typeof engine.config.max_input_bytes === "number" && (
                <>
                  <dt className="text-muted-foreground">Largest input sent</dt>
                  <dd>{formatBytes(engine.config.max_input_bytes)}</dd>
                </>
              )}
            </dl>
            <CommandHint
              commands={[
                `${ENGINES_CLI} budget ${engine.slug} --limit-usd ${engine.budget.limit_usd ?? 30}`,
                `${ENGINES_CLI} import-modal-toml --apply`,
              ]}
              note="Credentials are write-only: the API seals them and only worker-remote can open them. The UI never shows them."
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function LastTest({ engine }: { engine: Engine }) {
  const test = engine.config.last_test;
  if (!test) return <p className="text-sm text-muted-foreground">Never tested.</p>;
  return (
    <p className="text-sm flex flex-wrap items-center gap-2">
      <span className="text-muted-foreground">Last test</span>
      {test.ok ? <Pill tone="ok" icon={CheckCircle2}>passed</Pill> : <Pill tone="bad" icon={XCircle}>failed{test.code ? ` (${test.code})` : ""}</Pill>}
      <span className="text-xs text-muted-foreground">{formatAgo(test.at)}</span>
      {test.detail && <span className="text-xs text-muted-foreground w-full">{test.detail}</span>}
    </p>
  );
}

function LocalGpusCard({ engine }: { engine: Engine }) {
  const gpus = engine.config.gpus ?? [];
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Declared GPUs</CardTitle>
        <CardDescription>
          What capacity is validated against. <Link href="/admin/gpus" className="underline">GPUs</Link> compares
          them with what the workers detect.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {gpus.length === 0 ? (
          <p className="text-sm text-muted-foreground">None declared: every binding runs on CPU.</p>
        ) : (
          <ul className="text-sm space-y-1">
            {gpus.map((g) => (
              <li key={g.ref}>
                <code className="font-mono">{g.ref}</code> {g.name} · {g.vram_gb} GB · reserve {g.vram_reserve_gb ?? 1} GB
                {g.uuid && <span className="text-xs text-muted-foreground"> · {g.uuid}</span>}
              </li>
            ))}
          </ul>
        )}
        <CommandHint
          commands={[
            `${ENGINES_CLI} set-gpus ${
              gpus.length
                ? gpus.map(gpuArg).join(" ")
                : "gpu0:16:MyGPU"
            }`,
          ]}
          note="ref:vram_gb[:name[:uuid]]; every binding is revalidated against the new list."
        />
      </CardContent>
    </Card>
  );
}

/** One `set-gpus` argument, ref:vram_gb[:name[:uuid]], quoted when the name has spaces. */
function gpuArg(g: NonNullable<Engine["config"]["gpus"]>[number]) {
  const parts: (string | number)[] = [g.ref, g.vram_gb];
  if (g.name || g.uuid) parts.push(g.name ?? "");
  if (g.uuid) parts.push(g.uuid);
  const arg = parts.join(":");
  return /[\s"'$`\\]/.test(arg) ? `'${arg.replace(/'/g, "'\\''")}'` : arg;
}
