"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, Info } from "lucide-react";
import { computeApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CommandHint,
  ENGINES_CLI,
  Freshness,
  LoadingCards,
  QueryError,
  adminRetry,
} from "@/components/admin/compute-ui";
import {
  BudgetSummary,
  CredentialsSummary,
  EngineBadges,
  EngineIcon,
  FeatureCapacityRow,
  adapterLabel,
  isLocal,
} from "@/components/admin/engine-views";
import type { Engine, Feature } from "@/types/compute";
import { CreateEngine } from "@/components/admin/engine-control";

export default function EnginesPage() {
  const token = useAuthStore((s) => s.token);
  const query = useQuery({
    queryKey: ["admin", "engines", token],
    queryFn: computeApi.engines,
    enabled: !!token,
    refetchInterval: 15_000,
    retry: adminRetry,
  });

  if (query.isLoading) return <LoadingCards count={2} label="Loading engines" />;
  if (query.error && !query.data) {
    return <QueryError error={query.error} what="engines" onRetry={() => query.refetch()} />;
  }

  const engines = query.data ?? [];
  const remote = engines.filter((e) => !isLocal(e));
  const local = engines.find(isLocal);
  const localUnconfigured = local && Object.keys(local.features).length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {engines.length} engine{engines.length === 1 ? "" : "s"} · routing decides which one each feature uses.
        </p>
        <Freshness updatedAt={query.dataUpdatedAt} fetching={query.isFetching} />
      </div>

      <CreateEngine />

      {query.error ? <QueryError error={query.error} what="the latest engine state (showing the last one)" /> : null}

      {engines.length === 0 && (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            No engines yet. The built-in <code className="font-mono">local</code> engine is created when the API starts.
          </CardContent>
        </Card>
      )}

      {engines.map((engine) => (
        <EngineCard key={engine.id} engine={engine} />
      ))}

      {remote.length === 0 && local && <FreshInstallCard unconfigured={!!localUnconfigured} />}
    </div>
  );
}

function EngineCard({ engine }: { engine: Engine }) {
  const features = Object.entries(engine.features) as [Feature, NonNullable<Engine["features"][Feature]>][];
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <EngineIcon engine={engine} className="mt-1" />
            <div className="min-w-0">
              <CardTitle className="text-lg">
                <Link
                  href={`/admin/engines/${encodeURIComponent(engine.slug)}`}
                  className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {engine.display_name}
                </Link>
              </CardTitle>
              <CardDescription>
                <code className="font-mono">{engine.slug}</code> · {adapterLabel(engine.adapter_type)}
              </CardDescription>
            </div>
          </div>
          <EngineBadges engine={engine} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {engine.health_reason && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Why: </span>
            {engine.health_reason}
          </p>
        )}
        {engine.config_error && (
          <p className="flex items-start gap-1.5 text-sm text-red-700 dark:text-red-400">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
            {engine.config_error.message}
          </p>
        )}
        {features.length > 0 ? (
          <div className="grid gap-2 md:grid-cols-2">
            {features.map(([feature, cap]) => (
              <FeatureCapacityRow key={feature} engine={engine} feature={feature} cap={cap} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {isLocal(engine)
              ? "No capacity declared. Work still runs on this server's workers as before; capacity matters once a feature has a route."
              : "No feature bound yet."}
          </p>
        )}
        <div className="flex flex-wrap items-end justify-between gap-3 pt-1">
          <div className="space-y-1.5">
            <BudgetSummary engine={engine} compact />
            <CredentialsSummary engine={engine} />
          </div>
          <Link
            href={`/admin/engines/${encodeURIComponent(engine.slug)}`}
            className="inline-flex items-center text-sm font-medium text-primary hover:underline"
          >
            Details and commands
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

/** Only the local engine: say that this is complete, and how cloud capacity would be added. */
function FreshInstallCard({ unconfigured }: { unconfigured: boolean }) {
  return (
    <Card className="border-dashed">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Info className="h-4 w-4 text-muted-foreground" aria-hidden />
          Everything runs on this server
        </CardTitle>
        <CardDescription>
          That is all Ingestify needs. If jobs sometimes pile up, a cloud engine (a Modal account) can take the
          overflow, with a spending limit per period that it never goes past.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-primary hover:underline">
            How to set it up
          </summary>
          <div className="mt-3 space-y-3">
            {unconfigured && (
              <CommandHint
                title="1. Declare this server's GPU and how many replicas each feature runs"
                commands={[
                  `${ENGINES_CLI} set-gpus gpu0:16:MyGPU`,
                  `${ENGINES_CLI} set-capacity local transcription --workers 1 --gpu-ref gpu0`,
                ]}
              />
            )}
            <CommandHint
              title={`${unconfigured ? "2" : "1"}. Import a Modal account (created paused; dry run without --apply)`}
              commands={[`${ENGINES_CLI} import-modal-toml --limit-usd 30 --apply`]}
              note="Then bind, deploy, test and activate it, and add it to a route: see each engine's page and the Routing tab."
            />
          </div>
        </details>
      </CardContent>
    </Card>
  );
}
