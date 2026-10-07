"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { jobsApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { ImageView } from "./image-view";
import { FullAnalysisJobSidebar } from "./image-analysis/full-job-sidebar";
import { AnalysisStatus } from "./image-analysis/analysis-status";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import type { JobStatusResponse, JobResultResponse } from "@/types/api";

export function ImageJobWorkspace({ status, result, resultError, retryResult, onDelete, deleting }: {
 status: JobStatusResponse; result?: JobResultResponse; resultError: boolean; retryResult: () => void; onDelete: () => void; deleting: boolean;
}) {
 const [confirmDelete, setConfirmDelete] = useState(false);
 const client = useQueryClient();
 const cancel = useMutation({ mutationFn: () => jobsApi.cancelFullImage(status.job_id), onSuccess: () => client.invalidateQueries({ queryKey: ["job-status", status.job_id] }) });
 const composite = ["full", "faces"].includes(String(status.configuration?.options.mode));
 const running = ["queued", "processing"].includes(status.status);
 return <div className="flex min-h-screen flex-col bg-background lg:h-screen">
   <AppHeader />
   <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
     {composite ? <FullAnalysisJobSidebar status={status} onDelete={() => setConfirmDelete(true)} onCancel={() => cancel.mutate()} cancelling={cancel.isPending} /> :
       <aside className="space-y-4 border-b p-4 lg:w-60 lg:border-b-0 lg:border-r"><h1 className="break-words font-semibold">{status.name || "Análise de imagem"}</h1><AnalysisStatus status={status.status} /><details><summary>Configuração solicitada</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(status.configuration, null, 2)}</pre></details><Button variant="outline" onClick={() => setConfirmDelete(true)}>Excluir job</Button></aside>}
     <main className="min-w-0 flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
       {cancel.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(cancel.error)}</p>}
       {result?.result.image ? <ImageView image={result.result.image} fileName={status.name || status.job_id} /> :
         <div className="rounded-xl border p-8 text-center text-sm text-muted-foreground">
           {running ? "Análise em andamento. O relatório ficará disponível neste mesmo job." : resultError ? "Não foi possível carregar o relatório. Consulte este job novamente." : "Carregando o relatório…"}
           {!running && <Button variant="outline" className="ml-3" onClick={retryResult}>Tentar novamente</Button>}
         </div>}
     </main>
   </div>
   <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
     <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Excluir job?</AlertDialogTitle><AlertDialogDescription>A imagem e os resultados deste job serão excluídos.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancelar</AlertDialogCancel><AlertDialogAction disabled={deleting} onClick={onDelete}>Excluir</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
   </AlertDialog>
 </div>;
}
