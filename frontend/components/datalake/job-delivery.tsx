"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { datalakeApi } from "@/lib/datalake-api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { formatApiError } from "@/lib/utils";

export function JobDatalakeDelivery({ jobId, completed }: { jobId: string; completed: boolean }) {
  const token = useAuthStore((s) => s.token);
  const query = useQuery({ queryKey: ["datalake-delivery", token, jobId], queryFn: () => datalakeApi.delivery(jobId), enabled: !!token,
    refetchInterval: (q) => q.state.data?.destination && q.state.data.destination.status !== "completed" ? 5000 : false });
  const retry = useMutation({ mutationFn: () => datalakeApi.retry(jobId), onSuccess: () => query.refetch() });
  if (query.isError) return <div className="rounded-lg border p-4 text-sm" role="alert">Não foi possível consultar a entrega ao datalake. <Button variant="link" onClick={() => void query.refetch()}>Tentar novamente</Button></div>;
  const dest = query.data?.destination;
  if (!dest) return null;
  return <div className="space-y-2 rounded-lg border p-4 text-sm">
    <h3 className="font-semibold">Entrega ao datalake</h3>
    <p className="break-all">{dest.connection_name} · {dest.bucket}/{dest.resolved_path}/</p>
    {dest.layout_id && dest.partitioning?.mode !== "none" && <p className="text-xs text-muted-foreground">Layout: {dest.layout_id} · {dest.partitioning?.timezone}</p>}
    {dest.dataset_path && <p className="break-all font-mono text-xs">Dataset JSONL: {dest.dataset_path}</p>}
    <p role="status">{{ pending: completed ? "Aguardando entrega" : "Aguardando o resultado do job", exporting: "Entregando resultados…", completed: "Resultados entregues", failed: "Falha na entrega" }[dest.status]}</p>
    {dest.error && <p role="alert" className="text-destructive">{dest.error}</p>}
    {dest.status === "completed" && <details><summary className="cursor-pointer">Ver arquivos ({dest.objects.length})</summary><ul className="mt-2 space-y-1">{dest.objects.map((key) => <li className="break-all font-mono text-xs" key={key}>{key}</li>)}</ul></details>}
    {completed && dest.status === "failed" && <Button variant="outline" disabled={retry.isPending} onClick={() => retry.mutate()}>Tentar entrega novamente</Button>}
    {retry.isError && <p role="alert" className="text-destructive">{formatApiError(retry.error)}</p>}
  </div>;
}
