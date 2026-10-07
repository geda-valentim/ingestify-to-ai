"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Plus, Pencil, PlugZap, Trash2 } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConnectionEditor } from "@/components/datalake/connection-editor";
import { datalakeApi } from "@/lib/datalake-api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { formatApiError } from "@/lib/utils";
import { PROVIDER_LABELS, type DatalakeConnection } from "@/types/datalake";
import { PARTITION_LABELS } from "@/components/datalake/partition-editor";

export default function DatalakesPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const hydrated = useAuthStore((s) => s._hasHydrated);
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<DatalakeConnection | "new" | null>(null);
  const [remove, setRemove] = useState<DatalakeConnection | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  useEffect(() => { if (hydrated && (!user || !token)) router.replace(loginUrl()); }, [hydrated, user, token, router]);
  const query = useQuery({ queryKey: ["datalakes", token], queryFn: datalakeApi.list, enabled: !!token });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["datalakes"] });
  const test = useMutation({ mutationFn: (connection: DatalakeConnection) => datalakeApi.test(connection.id, connection.config.default_bucket ?? undefined),
    onSuccess: () => setFeedback("Conexão validada. O bucket pode ser escolhido na solicitação."), onMutate: () => setFeedback(null) });
  const toggle = useMutation({ mutationFn: (connection: DatalakeConnection) => datalakeApi.update(connection.id, { enabled: !connection.enabled }), onSuccess: refresh });
  const deletion = useMutation({ mutationFn: (connection: DatalakeConnection) => datalakeApi.remove(connection.id), onSuccess: () => { setRemove(null); void refresh(); } });
  if (!hydrated || !user) return null;
  return <div className="min-h-screen bg-background"><AppHeader />
    <main className="container mx-auto max-w-5xl space-y-6 p-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4"><div><h1 className="flex items-center gap-2 text-2xl font-bold"><Database className="h-6 w-6" />Datalakes</h1>
        <p className="mt-1 text-muted-foreground">Configure suas conexões. Escolha o bucket em cada solicitação.</p></div>
        <Button onClick={() => setEditor("new")}><Plus className="mr-2 h-4 w-4" />Nova conexão</Button></div>
      <p className="text-sm text-muted-foreground">AWS S3, MinIO, Google Cloud Storage e Azure Blob Storage. As credenciais são guardadas criptografadas no servidor e não são exibidas novamente.</p>
      {feedback && <p role="status" className="rounded-lg border border-green-600/30 bg-green-600/10 p-3 text-sm">{feedback}</p>}
      {(test.isError || toggle.isError) && <p role="alert" className="text-destructive">{formatApiError(test.error || toggle.error)}</p>}
      {query.isPending && <p role="status">Carregando conexões…</p>}
      {query.isError && <div role="alert">{formatApiError(query.error)} <Button variant="outline" onClick={() => void query.refetch()}>Tentar novamente</Button></div>}
      {query.isSuccess && !query.data.connections.length && <div className="rounded-lg border border-dashed p-8 text-center"><p className="font-medium">Nenhuma conexão cadastrada</p><p className="mt-1 text-sm text-muted-foreground">Adicione a conta de armazenamento que receberá seus resultados.</p></div>}
      <div className="grid gap-4 md:grid-cols-2">{query.data?.connections.map((connection) => <article key={connection.id} className="space-y-3 rounded-lg border p-5">
        <div className="flex items-start justify-between gap-2"><div><h2 className="text-lg font-semibold">{connection.name}</h2><p className="text-sm text-muted-foreground">{PROVIDER_LABELS[connection.provider]}</p></div><span className="text-xs">{connection.enabled ? "Ativa" : "Desativada"}</span></div>
        <p className="break-all text-sm">Bucket padrão: {connection.config.default_bucket || "Escolhido na solicitação"}</p>
        <p className="break-all text-xs text-muted-foreground">Pasta padrão: {connection.config.default_prefix || "Raiz do bucket"}</p>
        <p className="text-xs text-muted-foreground">Particionamento: {PARTITION_LABELS[connection.config.partitioning?.mode ?? "none"]}{connection.config.partitioning?.analytics === "jsonl" ? " · JSONL" : ""}</p>
        <div className="flex flex-wrap gap-1" aria-label="Buckets permitidos">{connection.config.buckets.length ? <>{connection.config.buckets.slice(0, 5).map((bucket) => <span key={bucket} className="max-w-full break-all rounded-md bg-muted px-2 py-1 text-xs">{bucket}</span>)}{connection.config.buckets.length > 5 && <span className="text-xs text-muted-foreground">+{connection.config.buckets.length - 5} buckets</span>}</> : <span className="text-xs text-muted-foreground">Todos os buckets acessíveis</span>}</div>
        {connection.config.endpoint && <p className="break-all text-xs text-muted-foreground">{connection.config.endpoint}</p>}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditor(connection)}><Pencil className="mr-1 h-4 w-4" />Editar</Button>
          <Button variant="outline" size="sm" disabled={test.isPending || !connection.enabled} onClick={() => test.mutate(connection)}><PlugZap className="mr-1 h-4 w-4" />Testar conexão</Button>
          <Button variant="ghost" size="sm" disabled={toggle.isPending} onClick={() => toggle.mutate(connection)}>{connection.enabled ? "Desativar" : "Ativar"}</Button>
          <Button variant="ghost" size="sm" onClick={() => { deletion.reset(); setRemove(connection); }} aria-label={`Excluir ${connection.name}`}><Trash2 className="h-4 w-4" /></Button>
        </div>
      </article>)}</div>
      {editor && <ConnectionEditor key={typeof editor === "string" ? "new" : editor.id} connection={editor === "new" ? null : editor}
        onClose={() => setEditor(null)} onSaved={() => { setEditor(null); void refresh(); }} />}
      <Dialog open={!!remove} onOpenChange={(open) => { if (!open) setRemove(null); }}><DialogContent><DialogHeader><DialogTitle>Excluir conexão?</DialogTitle>
        <DialogDescription>Esta ação remove {remove?.name} do Ingestify. Os arquivos no bucket permanecem no datalake.</DialogDescription></DialogHeader>
        {deletion.isError && <p role="alert" className="text-destructive">{formatApiError(deletion.error)}</p>}
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setRemove(null)}>Cancelar</Button><Button variant="destructive" disabled={deletion.isPending} onClick={() => remove && deletion.mutate(remove)}>Excluir conexão</Button></div>
      </DialogContent></Dialog>
    </main>
  </div>;
}
