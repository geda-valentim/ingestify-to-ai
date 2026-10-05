"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, HelpCircle, Radio } from "lucide-react";
import { computeApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CommandHint,
  Freshness,
  HealthBadge,
  LoadingCards,
  Meter,
  Pill,
  QueryError,
  StatusBadge,
  adminRetry,
  featureTitle,
  formatAgo,
  formatSeconds,
} from "@/components/admin/compute-ui";
import type { DispatcherLease, EnginesStatus, Feature } from "@/types/compute";
import { FEATURES } from "@/types/compute";

// Same default as a route's dispatcher_down_seconds: past it the dispatcher counts as down.
const DISPATCHER_DOWN_SECONDS = 120;

export default function StatusPage() {
  const token = useAuthStore((s) => s.token);
  const query = useQuery({
    queryKey: ["admin", "engines-status", token],
    queryFn: computeApi.status,
    enabled: !!token,
    refetchInterval: 10_000,
    retry: adminRetry,
  });

  if (query.isLoading) return <LoadingCards count={3} label="Loading status" />;
  if (query.error && !query.data) {
    return <QueryError error={query.error} what="the dispatcher status" onRetry={() => query.refetch()} />;
  }
  const status = query.data!;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Live view, refreshed every 10 seconds.</p>
        <Freshness updatedAt={query.dataUpdatedAt} fetching={query.isFetching} />
      </div>
      {query.error ? <QueryError error={query.error} what="the latest status (showing the last one)" /> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <DispatcherCard lease={status.dispatcher} />
        <RemoteWorkerCard status={status} />
      </div>
      <CapacityCard status={status} />
      <BacklogCard status={status} />
    </div>
  );
}

function DispatcherCard({ lease }: { lease: DispatcherLease }) {
  const seen = lease.dispatcher_seen_seconds_ago;
  const up = seen !== null && seen <= DISPATCHER_DOWN_SECONDS;
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Dispatcher</CardTitle>
            <CardDescription>worker-dispatch: places backlog items on engines by route</CardDescription>
          </div>
          {seen === null ? (
            <Pill tone="muted" icon={HelpCircle}>Never seen</Pill>
          ) : up ? (
            <Pill tone="ok" icon={CheckCircle2}>Running</Pill>
          ) : (
            <Pill tone="warn" icon={AlertTriangle}>Not seen</Pill>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-2 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Last seen</dt>
          <dd>{seen === null ? "never" : `${formatSeconds(seen)} ago`}</dd>
          <dt className="text-muted-foreground">Lease epoch</dt>
          <dd className="tabular-nums">{lease.epoch}</dd>
          <dt className="text-muted-foreground">Holder</dt>
          <dd className="break-all">
            {lease.holder ?? "none"}
            {lease.holder_kind && <span className="text-muted-foreground"> ({lease.holder_kind})</span>}
          </dd>
          <dt className="text-muted-foreground">Renewed</dt>
          <dd>{formatAgo(lease.renewed_at)}</dd>
        </dl>
        {!up && (
          <CommandHint
            title="Only needed once a feature has a route"
            commands={["docker compose --profile engines up -d worker-dispatch"]}
            note="While it is down, a route's dispatcher_fallback decides: local work goes straight to the local workers, or waits."
          />
        )}
      </CardContent>
    </Card>
  );
}

function RemoteWorkerCard({ status }: { status: EnginesStatus }) {
  const hb = status.remote_worker;
  const hasRemote = status.engines.some((r) => r.adapter_type !== "local");
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Remote worker</CardTitle>
            <CardDescription>worker-remote: runs cloud work; the only holder of the credential key</CardDescription>
          </div>
          {hb ? (
            <Pill tone="ok" icon={Radio}>Alive</Pill>
          ) : (
            <Pill tone={hasRemote ? "warn" : "muted"} icon={hasRemote ? AlertTriangle : HelpCircle}>
              Not running
            </Pill>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {hb ? (
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Host</dt>
            <dd className="break-all">{hb.hostname ?? "—"}</dd>
            <dt className="text-muted-foreground">Threads</dt>
            <dd className="tabular-nums">{hb.concurrency ?? "—"}</dd>
            <dt className="text-muted-foreground">Private key loaded</dt>
            <dd>{hb.private_keys === "yes" ? "yes" : "no"}</dd>
            <dt className="text-muted-foreground">Heartbeat</dt>
            <dd>{hb.updated_at ? formatAgo(new Date(Number(hb.updated_at) * 1000).toISOString()) : "—"}</dd>
          </dl>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              {hasRemote
                ? "Cloud engines cannot run, be tested or be added to a route while it is down."
                : "Not needed without cloud engines."}
            </p>
            {hasRemote && (
              <CommandHint commands={["docker compose --profile engines up -d --build worker-remote"]} />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function CapacityCard({ status }: { status: EnginesStatus }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">In flight per engine and feature</CardTitle>
        <CardDescription>Only routed work is counted; today&apos;s direct path is not.</CardDescription>
      </CardHeader>
      <CardContent>
        {status.engines.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No capacity declared on any engine. See <Link href="/admin/engines" className="underline">Engines</Link>.
          </p>
        ) : (
          <ul className="space-y-3">
            {status.engines.map((row) => (
              <li key={`${row.engine}-${row.feature}`} className="rounded-md border p-3 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm">
                    <Link href={`/admin/engines/${encodeURIComponent(row.engine)}`} className="font-medium hover:underline">
                      {row.engine}
                    </Link>{" "}
                    <span className="text-muted-foreground">· {featureTitle(row.feature)}</span>
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusBadge status={row.status} />
                    <HealthBadge health={row.health} />
                  </div>
                </div>
                <Meter
                  label="In flight / capacity"
                  value={row.in_flight}
                  max={row.capacity}
                  valueText={`${row.in_flight} of ${row.capacity}`}
                />
                <p className="text-xs text-muted-foreground">
                  {row.workers_configured !== undefined &&
                    `configured ${row.workers_configured}, alive ${row.workers_alive ?? "unknown"}`}
                  {row.fallback_in_flight > 0 && ` · ${row.fallback_in_flight} via fallback`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function BacklogCard({ status }: { status: EnginesStatus }) {
  const features = (Object.keys(status.backlog) as Feature[]).sort(
    (a, b) => FEATURES.indexOf(a) - FEATURES.indexOf(b)
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Backlog</CardTitle>
        <CardDescription>Items waiting for a placement, per feature.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Backlog per feature</caption>
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="font-medium py-1">Feature</th>
              <th className="font-medium py-1 text-right">Waiting</th>
              <th className="font-medium py-1 text-right">Oldest</th>
              <th className="font-medium py-1 text-right">Assigned</th>
              <th className="font-medium py-1 text-right">Running</th>
              <th className="font-medium py-1 text-right">Bypassed 24 h</th>
            </tr>
          </thead>
          <tbody>
            {features.map((feature) => {
              const b = status.backlog[feature];
              return (
                <tr key={feature} className="border-t">
                  <td className="py-1.5">{featureTitle(feature)}</td>
                  <td className="py-1.5 text-right tabular-nums">{b.waiting}</td>
                  <td className="py-1.5 text-right tabular-nums">{formatSeconds(b.oldest_wait_seconds)}</td>
                  <td className="py-1.5 text-right tabular-nums">{b.by_state.assigned ?? 0}</td>
                  <td className="py-1.5 text-right tabular-nums">{b.by_state.running ?? 0}</td>
                  <td className="py-1.5 text-right tabular-nums">{b.bypassed_24h}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
