"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, CheckCircle2, Cloud, Hourglass, Server } from "lucide-react";
import { computeApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CommandHint,
  EngineLink,
  ENGINES_CLI,
  Freshness,
  LoadingCards,
  Pill,
  QueryError,
  adminRetry,
  featureTitle,
  formatAgo,
  formatSeconds,
  formatUsd,
} from "@/components/admin/compute-ui";
import type { Backlog, ExplicitRoute, FeatureRoute, RouteStep } from "@/types/compute";

export default function RoutingPage() {
  const token = useAuthStore((s) => s.token);
  const query = useQuery({
    queryKey: ["admin", "routing", token],
    queryFn: computeApi.routing,
    enabled: !!token,
    refetchInterval: 15_000,
    retry: adminRetry,
  });

  if (query.isLoading) return <LoadingCards count={3} label="Loading routes" />;
  if (query.error && !query.data) {
    return <QueryError error={query.error} what="routes" onRetry={() => query.refetch()} />;
  }
  const routes = query.data ?? [];
  const allImplicit = routes.every((r) => r.implicit);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          A route sends a feature&apos;s work through a backlog that the dispatcher places step by step. Without one,
          the feature runs exactly as before.
        </p>
        <Freshness updatedAt={query.dataUpdatedAt} fetching={query.isFetching} />
      </div>
      {query.error ? <QueryError error={query.error} what="the latest routes (showing the last ones)" /> : null}
      {allImplicit && routes.length > 0 && (
        <p className="text-sm rounded-md border bg-muted/40 p-3">
          No feature has a route: everything runs on this server&apos;s workers, as it always has. Routes matter once
          you add a <EngineLink href="/admin/engines" className="underline">cloud engine</EngineLink> for overflow.
        </p>
      )}
      {routes.map((route) => (
        <RouteCard key={route.feature} route={route} />
      ))}
    </div>
  );
}

function RouteCard({ route }: { route: FeatureRoute }) {
  return (
    <Card id={route.feature}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">{featureTitle(route.feature)}</CardTitle>
            <CardDescription>
              {route.implicit
                ? "Implicit: local only (today's behaviour)"
                : `Version ${route.version} · changed ${formatAgo(route.updated_at)}`}
            </CardDescription>
          </div>
          {route.implicit ? (
            <Pill tone="muted" icon={Server}>Local only</Pill>
          ) : route.state === "draining" ? (
            <Pill tone="warn" icon={Hourglass} title="Removed: its backlog drains back to today's path">Draining</Pill>
          ) : (
            <Pill tone="ok" icon={CheckCircle2}>Active</Pill>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {route.implicit ? (
          <p className="text-sm text-muted-foreground">
            Work goes straight to the feature&apos;s own queue on this server: no backlog, no dispatcher.
          </p>
        ) : (
          <ExplicitRouteBody route={route} />
        )}
        {route.backlog && <BacklogLine backlog={route.backlog} implicit={route.implicit} />}
        <CommandHint
          commands={
            route.implicit
              ? [`${ENGINES_CLI} routes set ${route.feature} --step local --step "modal_1 min_wait=600"`]
              : [routeSetCommand(route), `${ENGINES_CLI} routes delete ${route.feature}`]
          }
          note={
            route.implicit
              ? "Example: local first, a cloud engine after 10 min of waiting. Needs worker-dispatch (docker compose --profile engines up -d worker-dispatch)."
              : "routes set replaces the whole route; routes delete drains its backlog back to today's path."
          }
        />
      </CardContent>
    </Card>
  );
}

function ExplicitRouteBody({ route }: { route: ExplicitRoute }) {
  return (
    <div className="space-y-4">
      <ol className="space-y-2" aria-label="Steps, tried in order">
        {route.steps.map((step, i) => (
          <li key={i}>
            {i > 0 && <ArrowDown className="h-4 w-4 text-muted-foreground mx-auto mb-2" aria-hidden />}
            <StepRow step={step} index={i} />
          </li>
        ))}
      </ol>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <Term label="No engine available">
          {route.on_no_engine === "hold"
            ? "keep waiting"
            : `fail after ${formatSeconds(route.fail_after_seconds)}`}
        </Term>
        <Term label="Attempts per item">{route.max_attempts}</Term>
        <Term label="Cloud engines usable by">
          {route.remote_allowed_for === "all" ? "every user" : "restricted (needs the remote engine permission)"}
        </Term>
        <Term label="Per-user limit per period">
          {route.user_period_limit_usd === null ? "none" : formatUsd(route.user_period_limit_usd)}
        </Term>
        <Term label="If the dispatcher is down">
          {route.dispatcher_fallback === "local_direct" ? "send new work straight to local workers" : "hold it"} (after{" "}
          {formatSeconds(route.dispatcher_down_seconds)})
        </Term>
      </dl>
      {route.remote_data_notice && (
        <p className="text-xs text-muted-foreground">Notice shown to users: {route.remote_data_notice}</p>
      )}
    </div>
  );
}

function Term({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b py-1">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

function StepRow({ step, index }: { step: RouteStep; index: number }) {
  const conditions: string[] = [];
  if (step.when?.min_wait_seconds) conditions.push(`an item has waited ≥ ${formatSeconds(step.when.min_wait_seconds)}`);
  if (step.when?.min_backlog) conditions.push(`backlog ≥ ${step.when.min_backlog}`);
  return (
    <div className="rounded-md border p-3 space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-semibold">
          {index + 1}
        </span>
        {step.engines.map((e) => (
          <EngineLink
            key={e.id}
            href={`/admin/engines/${encodeURIComponent(e.slug ?? e.id)}`}
            className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-sm hover:bg-muted"
          >
            {e.adapter_type === "local" ? <Server className="h-3.5 w-3.5" aria-hidden /> : <Cloud className="h-3.5 w-3.5" aria-hidden />}
            {e.slug ?? `${e.id.slice(0, 8)} (deleted)`}
          </EngineLink>
        ))}
        {step.engines.length > 1 && (
          <span className="text-xs text-muted-foreground">
            {step.group_strategy === "fill_first" ? "fill the first before the next" : "first available, in order"}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {conditions.length ? `Used when ${conditions.join(" and ")}` : "Used whenever it has room"}
        {step.scale_out_after_seconds ? ` · next engine of the group after ${formatSeconds(step.scale_out_after_seconds)}` : ""}
        {step.spend_cap ? ` · spend cap ${formatUsd(step.spend_cap.usd)} per ${step.spend_cap.window}` : ""}
      </p>
    </div>
  );
}

function BacklogLine({ backlog, implicit }: { backlog: Backlog; implicit: boolean }) {
  const active = Object.entries(backlog.by_state).filter(([state, n]) => n > 0 && state !== "done" && state !== "failed");
  if (implicit && backlog.waiting === 0 && active.length === 0) return null;
  return (
    <div className="text-sm space-y-1">
      <p>
        <span className="font-medium">{backlog.waiting}</span> waiting
        {backlog.oldest_wait_seconds !== null && <> · oldest {formatSeconds(backlog.oldest_wait_seconds)}</>}
        {backlog.fallback_in_flight > 0 && <> · {backlog.fallback_in_flight} running through the fallback</>}
        {backlog.bypassed_24h > 0 && <> · {backlog.bypassed_24h} bypassed the dispatcher in 24 h</>}
      </p>
      {active.length > 0 && (
        <p className="text-xs text-muted-foreground">{active.map(([state, n]) => `${state} ${n}`).join(" · ")}</p>
      )}
    </div>
  );
}

/** The `routes set` line that would recreate this route as it is now. */
function routeSetCommand(route: ExplicitRoute) {
  const parts = [`${ENGINES_CLI} routes set ${route.feature}`];
  for (const step of route.steps) {
    const opts = [step.engines.map((e) => e.slug ?? e.id).join(",")];
    if (step.group_strategy === "fill_first") opts.push("fill_first");
    if (step.when?.min_wait_seconds) opts.push(`min_wait=${step.when.min_wait_seconds}`);
    if (step.when?.min_backlog) opts.push(`min_backlog=${step.when.min_backlog}`);
    if (step.scale_out_after_seconds) opts.push(`scale_out=${step.scale_out_after_seconds}`);
    if (step.spend_cap) opts.push(`cap=${step.spend_cap.usd}/${step.spend_cap.window}`);
    const text = opts.join(" ");
    parts.push(`--step ${opts.length > 1 ? `"${text}"` : text}`);
  }
  if (route.max_attempts !== 3) parts.push(`--max-attempts ${route.max_attempts}`);
  if (route.dispatcher_fallback !== "local_direct") parts.push(`--fallback ${route.dispatcher_fallback}`);
  if (route.on_no_engine === "fail") parts.push(`--on-no-engine fail --fail-after ${route.fail_after_seconds ?? 3600}`);
  return parts.join(" ");
}
