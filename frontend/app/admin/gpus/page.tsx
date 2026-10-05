"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, HelpCircle, MemoryStick } from "lucide-react";
import { computeApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CommandHint,
  ENGINES_CLI,
  Freshness,
  LoadingCards,
  Meter,
  Pill,
  QueryError,
  adminRetry,
  featureTitle,
} from "@/components/admin/compute-ui";
import type { DetectedGpu, PhysicalGpu } from "@/types/compute";

export default function GpusPage() {
  const token = useAuthStore((s) => s.token);
  const query = useQuery({
    queryKey: ["admin", "gpus", token],
    queryFn: computeApi.gpus,
    enabled: !!token,
    refetchInterval: 15_000,
    retry: adminRetry,
  });

  if (query.isLoading) return <LoadingCards count={1} label="Loading GPUs" />;
  if (query.error && !query.data) {
    return <QueryError error={query.error} what="GPUs" onRetry={() => query.refetch()} />;
  }
  const { declared, undeclared_detected: undeclared } = query.data!;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          This server&apos;s GPUs as declared on the local engine, against what worker heartbeats report.
        </p>
        <Freshness updatedAt={query.dataUpdatedAt} fetching={query.isFetching} />
      </div>
      {query.error ? <QueryError error={query.error} what="the latest GPU state (showing the last one)" /> : null}

      {declared.length === 0 && undeclared.length === 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">No GPU declared or detected</CardTitle>
            <CardDescription>
              Without a declared GPU every local binding runs on CPU. If this server has one, declare it so capacity
              is checked against its memory.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CommandHint commands={[`${ENGINES_CLI} set-gpus gpu0:16:MyGPU`]} note="ref:vram_gb[:name[:uuid]]" />
          </CardContent>
        </Card>
      )}

      {query.data?.live_worker && <Card><CardHeader><CardTitle className="text-base">Live transcription</CardTitle>
        <CardDescription>{query.data.live_worker.model} · {query.data.live_worker.ready ? "Ready" : "Not ready"} · {query.data.live_worker.capacity} simultaneous sessions</CardDescription>
        </CardHeader><CardContent className="text-sm">Resident GPU budget: {query.data.live_worker.resident_vram_gb} GB. This service receives continuous audio over WebSocket.</CardContent></Card>}

      {declared.map((gpu) => (
        <DeclaredGpuCard key={gpu.ref} gpu={gpu} />
      ))}
      {undeclared.map((gpu) => (
        <UndeclaredGpuCard key={gpu.uuid} gpu={gpu} />
      ))}

      {declared.length > 0 && (
        <CommandHint
          commands={[
            `${ENGINES_CLI} set-gpus gpu0:16:MyGPU:GPU-<uuid>`,
            `${ENGINES_CLI} set-capacity local transcription --workers 2 --gpu-ref gpu0`,
          ]}
          note="Every binding on a GPU is revalidated against its VRAM; a change that does not fit is refused with the sum."
        />
      )}
    </div>
  );
}

function DeclaredGpuCard({ gpu }: { gpu: PhysicalGpu }) {
  const usable = gpu.vram_gb;
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <MemoryStick className="h-4 w-4 text-muted-foreground" aria-hidden />
              <code className="font-mono">{gpu.ref}</code> {gpu.name}
            </CardTitle>
            <CardDescription>
              {gpu.vram_gb} GB · reserve {gpu.reserve_gb} GB{gpu.uuid ? ` · ${gpu.uuid}` : " · no UUID declared"}
            </CardDescription>
          </div>
          {gpu.detected ? (
            <Pill tone="ok" icon={CheckCircle2}>Detected</Pill>
          ) : gpu.uuid ? (
            <Pill tone="warn" icon={AlertTriangle} title="No live worker reports this UUID">Not seen</Pill>
          ) : (
            <Pill tone="muted" icon={HelpCircle} title="Declare the UUID to match it with worker heartbeats">
              Not matched
            </Pill>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Meter
          label="Budgeted (bindings + live + reserve)"
          value={gpu.budgeted_gb}
          max={usable}
          valueText={`${gpu.budgeted_gb} of ${usable} GB${gpu.budgeted_gb > usable ? " — over" : ""}`}
        />
        {!!gpu.live_reserved_gb && <p className="text-xs text-muted-foreground">Includes {gpu.live_reserved_gb} GB reserved for the live resident model.</p>}
        {gpu.used_gb !== null ? (
          <Meter
            label="Used now (nvidia-smi via heartbeat)"
            value={gpu.used_gb}
            max={usable}
            valueText={`${gpu.used_gb} of ${usable} GB`}
          />
        ) : (
          <p className="text-xs text-muted-foreground">Used now: unknown (no heartbeat matched to this GPU).</p>
        )}
        {gpu.bindings.length > 0 ? (
          <table className="w-full text-sm">
            <caption className="sr-only">Features budgeted on {gpu.ref}</caption>
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="font-medium py-1">Feature</th>
                <th className="font-medium py-1 text-right">Replicas × at a time</th>
                <th className="font-medium py-1 text-right">GB each</th>
                <th className="font-medium py-1 text-right">GB total</th>
              </tr>
            </thead>
            <tbody>
              {gpu.bindings.map((b) => (
                <tr key={b.feature} className="border-t">
                  <td className="py-1">{featureTitle(b.feature)}</td>
                  <td className="py-1 text-right tabular-nums">
                    {b.workers} × {b.executions_per_worker}
                  </td>
                  <td className="py-1 text-right tabular-nums">{b.vram_each_gb}</td>
                  <td className="py-1 text-right tabular-nums">
                    {Math.round(b.workers * b.executions_per_worker * b.vram_each_gb * 100) / 100}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground">No feature bound to this GPU.</p>
        )}
      </CardContent>
    </Card>
  );
}

function UndeclaredGpuCard({ gpu }: { gpu: DetectedGpu }) {
  return (
    <Card className="border-amber-600/40">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">{gpu.name ?? "GPU"}</CardTitle>
            <CardDescription>{gpu.uuid}</CardDescription>
          </div>
          <Pill tone="warn" icon={AlertTriangle}>Detected, not declared</Pill>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Meter
          label="Used now"
          value={gpu.vram_used_gb}
          max={gpu.vram_total_gb}
          valueText={`${gpu.vram_used_gb} of ${gpu.vram_total_gb} GB`}
        />
        <p className="text-xs text-muted-foreground">
          Workers on it: {gpu.workers.map((w) => `${featureTitle(w.feature)} (${w.hostname})`).join(", ")}
        </p>
        <CommandHint
          commands={[
            `${ENGINES_CLI} set-gpus gpu0:${Math.floor(gpu.vram_total_gb)}:${(gpu.name ?? "GPU").replace(/[^A-Za-z0-9_-]/g, "")}:${gpu.uuid}`,
          ]}
          note="Declaring it lets capacity be checked against its memory. List every GPU in one call: set-gpus replaces the list."
        />
      </CardContent>
    </Card>
  );
}
