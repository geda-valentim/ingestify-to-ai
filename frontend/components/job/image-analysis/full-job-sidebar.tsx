"use client";

import Link from "next/link";
import { FileImage, Folder, Loader2, Trash2 } from "lucide-react";
import { parseApiDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { JobTagsCard } from "../job-tags-card";
import { JobDatalakeDelivery } from "@/components/datalake/job-delivery";
import type { JobStatusResponse } from "@/types/api";
import { AnalysisStatus } from "./analysis-status";

export function FullAnalysisJobSidebar({
  status,
  onDelete,
  onCancel,
  cancelling,
}: {
  status: JobStatusResponse;
  onDelete: () => void;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const running = ["pending", "queued", "processing"].includes(status.status);
  const analysis = status.image_analysis;
  return (
    <aside className="min-w-0 space-y-4 border-b p-4 lg:w-60 lg:shrink-0 lg:overflow-y-auto lg:border-b-0 lg:border-r xl:w-64">
      <div className="flex items-start gap-3">
        <FileImage className="mt-1 h-5 w-5 shrink-0 text-primary" />
        <div className="min-w-0">
          <h1 className="break-words text-base font-semibold">
            {status.name || "Análise de imagem"}
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            {status.configuration?.options?.mode === "faces" ? "Rostos e expressões" : "Análise completa da imagem"}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <AnalysisStatus status={status.status} />
        {status.project && (
          <Link
            href={`/jobs?project_id=${encodeURIComponent(status.project.id)}`}
            className="inline-flex min-w-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <Folder className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{status.project.name}</span>
          </Link>
        )}
      </div>
      {running && (
        <section
          className="space-y-3 rounded-xl border bg-card p-3"
          aria-label="Progresso da análise"
        >
          <div className="flex justify-between text-xs">
            <span>Progresso</span>
            <span className="tabular-nums">{status.progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${status.progress}%` }}
            />
          </div>
          {analysis && (
            <p className="text-xs text-muted-foreground">
              {analysis.steps_completed}/{analysis.steps_total} etapas
              concluídas
            </p>
          )}
          <Button
            size="sm"
            variant="outline"
            className="w-full"
            disabled={cancelling || analysis?.cancel_requested}
            onClick={onCancel}
          >
            {cancelling && (
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
            )}
            {analysis?.cancel_requested
              ? "Cancelamento solicitado"
              : "Cancelar análise"}
          </Button>
        </section>
      )}
      <details className="group rounded-xl border bg-card p-3">
        <summary className="cursor-pointer text-sm font-medium">
          Detalhes e organização
        </summary>
        <div className="mt-4 space-y-4">
          <dl className="space-y-3 text-xs">
            <div>
              <dt className="text-muted-foreground">ID do job</dt>
              <dd className="mt-1 break-all font-mono">{status.job_id}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Criado em</dt>
              <dd className="mt-1">
                {status.created_at
                  ? parseApiDate(status.created_at).toLocaleString("pt-BR")
                  : "—"}
              </dd>
            </div>
          </dl>
          {status.configuration && (
            <details>
              <summary className="cursor-pointer text-xs font-medium">
                Configuração solicitada
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
                {JSON.stringify(status.configuration, null, 2)}
              </pre>
            </details>
          )}
          <JobTagsCard jobId={status.job_id} tags={status.tags ?? []} />
          <Button
            size="sm"
            variant="outline"
            className="w-full text-destructive hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Excluir job
          </Button>
        </div>
      </details>
      <JobDatalakeDelivery
        jobId={status.job_id}
        completed={status.status === "completed" || status.status === "partial"}
      />
      {status.error && (
        <p className="break-words text-xs text-destructive" role="alert">
          {status.error}
        </p>
      )}
    </aside>
  );
}
